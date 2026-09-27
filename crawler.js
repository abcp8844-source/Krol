const { createClient } = require('@supabase/supabase-js');
const axios = require('axios');
const cheerio = require('cheerio');

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_KEY;
const supabase = createClient(supabaseUrl, supabaseKey);

const userAgents = [
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
];

function getRandomUserAgent() {
  return userAgents[Math.floor(Math.random() * userAgents.length)];
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms + Math.floor(Math.random() * 1000)));
}

async function resolveDeepTargetUrl(initialUrl, jobTitle) {
  let currentUrl = initialUrl;
  let hops = 0;
  const maxHops = 8;

  while (hops < maxHops) {
    try {
      const response = await axios.get(currentUrl, {
        headers: { 'User-Agent': getRandomUserAgent() },
        maxRedirects: 5,
        timeout: 10000
      });

      const $ = cheerio.load(response.data);
      const pageText = $('body').text().toLowerCase();

      if (currentUrl.includes('facebook.com') || currentUrl.includes('t.co') || currentUrl.includes('redirect') || currentUrl.includes('l.facebook.com')) {
        let bestCandidateLink = null;
        
        $('a').each((_, element) => {
          const href = $(element).attr('href');
          const linkText = $(element).text().toLowerCase();
          
          if (href && href.startsWith('http') && !href.includes('facebook.com') && !href.includes('google.com') && !href.includes('twitter.com')) {
            if (jobTitle && pageText.includes(jobTitle.toLowerCase())) {
              bestCandidateLink = href;
              return false;
            } else if (!bestCandidateLink) {
              bestCandidateLink = href;
            }
          }
        });

        if (bestCandidateLink) {
          currentUrl = bestCandidateLink;
          hops++;
          await delay(1500);
          continue;
        }
      }
      break;
    } catch (err) {
      break;
    }
  }
  return currentUrl;
}

async function extractJobDetails(targetUrl) {
  try {
    const response = await axios.get(targetUrl, {
      headers: { 'User-Agent': getRandomUserAgent() },
      timeout: 10000
    });

    const $ = cheerio.load(response.data);
    const pageText = $('body').text();

    let salary = "Not Specified";
    const salaryMatch = pageText.match(/(\$|€|£|Rs\.?|PKR|USD)\s*[\d,]+(\.\d+)?(\s*-\s*[\d,]+)?/i);
    if (salaryMatch) {
      salary = salaryMatch[0];
    }

    let location = "Remote / On-site";
    const locationMatch = pageText.match(/(Location|City|Address):\s*([A-Za-z\s,]+)/i);
    if (locationMatch) {
      location = locationMatch[2].trim().substring(0, 50);
    }

    return {
      finalUrl: targetUrl,
      salary: salary,
      location: location,
      snippet: pageText.substring(0, 400)
    };
  } catch (error) {
    return null;
  }
}

async function runDeepCrawler() {
  const { data: rawJobs, error } = await supabase
    .from('raw_jobs')
    .select('*')
    .eq('is_enriched', false)
    .limit(10);

  if (error || !rawJobs || rawJobs.length === 0) {
    return;
  }

  for (const job of rawJobs) {
    const resolvedUrl = await resolveDeepTargetUrl(job.source_link, job.title);
    const enrichedData = await extractJobDetails(resolvedUrl);

    if (enrichedData) {
      await supabase
        .from('raw_jobs')
        .update({
          source_link: enrichedData.finalUrl,
          salary: enrichedData.salary,
          location: enrichedData.location,
          snippet: enrichedData.snippet,
          is_enriched: true
        })
        .eq('id', job.id);
    }

    await delay(2000);
  }
}

runDeepCrawler();
