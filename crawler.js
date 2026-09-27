const axios = require('axios');
const cheerio = require('cheerio');
const { getRandomUserAgent, delay } = require('./anti-block');

async function fetchRawJobsFromDB() {
  try {
    const response = await axios.get('https://your-domain.com/api/get-raw-jobs');
    return response.data;
  } catch (error) {
    console.error("DB Fetch Error:", error.message);
    return [];
  }
}

async function resolveDeepTargetUrl(initialUrl) {
  let currentUrl = initialUrl;
  let hops = 0;
  const maxHops = 6;

  while (hops < maxHops) {
    try {
      const response = await axios.get(currentUrl, {
        headers: { 'User-Agent': getRandomUserAgent() },
        maxRedirects: 5,
        timeout: 10000
      });

      const $ = cheerio.load(response.data);

      if (currentUrl.includes('facebook.com') || currentUrl.includes('t.co') || currentUrl.includes('redirect')) {
        let externalLink = null;
        $('a').each((_, element) => {
          const href = $(element).attr('href');
          if (href && href.startsWith('http') && !href.includes('facebook.com') && !href.includes('google.com')) {
            externalLink = href;
            return false;
          }
        });

        if (externalLink) {
          currentUrl = externalLink;
          hops++;
          await delay(2000);
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

    let salary = "تلاش جاری ہے / طے شدہ نہیں";
    let location = "آن لائن / لوکل";

    if (pageText.match(/\$|\€|\£|Rs|PKR|USD|Salary|Pay/i)) {
      salary = "تفصیلات میں دستیاب ہے";
    }

    return {
      finalUrl: targetUrl,
      salary: salary,
      location: location,
      snippet: pageText.substring(0, 300)
    };
  } catch (error) {
    return null;
  }
}

async function runDeepCrawler() {
  const rawJobs = await fetchRawJobsFromDB();
  if (rawJobs.length === 0) return;

  for (const job of rawJobs) {
    const resolvedUrl = await resolveDeepTargetUrl(job.source_link);
    const enrichedData = await extractJobDetails(resolvedUrl);

    if (enrichedData) {
      await axios.post('https://your-domain.com/api/update-job', {
        id: job.id,
        finalUrl: enrichedData.finalUrl,
        salary: enrichedData.salary,
        location: enrichedData.location,
        snippet: enrichedData.snippet
      });
    }
    await delay(3000);
  }
}

runDeepCrawler();
