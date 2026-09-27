const { createClient } = require('@supabase/supabase-js');

// آپ اپنے ماحول کے مطابق یہاں اپنی سپابیس یا ڈیٹا بیس کی کرڈینشلز سیٹ کریں گے
const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_KEY;
const supabase = createClient(supabaseUrl, supabaseKey);

async function getRawJobs() {
  const { data, error } = await supabase
    .from('raw_jobs')
    .select('*')
    .eq('is_enriched', false)
    .limit(10);

  if (error) {
    console.error("DB Fetch Error:", error.message);
    return [];
  }
  return data;
}

async function updateEnrichedJob(id, finalUrl, salary, location, snippet) {
  const { error } = await supabase
    .from('raw_jobs')
    .update({
      source_link: finalUrl,
      salary: salary,
      location: location,
      snippet: snippet,
      is_enriched: true
    })
    .eq('id', id);

  if (error) {
    console.error("DB Update Error:", error.message);
  }
}

module.exports = { getRawJobs, updateEnrichedJob };
