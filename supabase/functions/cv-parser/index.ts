// Supabase Edge Function: proxy between the Lovable dashboard and the cv_parser API.
// Keeps CV_PARSER_API_TOKEN on the server. Requires a valid Supabase user JWT (verify_jwt = true, the default).
//
//   POST  (multipart, field "file")  -> 202 { job_id, status: "queued" }
//   POST  (json) { job_id }          -> 200 { job_id, status, result, error }   (or GET ?job_id=<id>)
//
// Secrets: CV_PARSER_URL (e.g. https://cv-parser.onrender.com), CV_PARSER_API_TOKEN

const MAX_BYTES = 10 * 1024 * 1024;
const ALLOWED = [".pdf", ".docx", ".jpg", ".jpeg", ".png"];

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });

  const baseUrl = Deno.env.get("CV_PARSER_URL")?.replace(/\/$/, "");
  const token = Deno.env.get("CV_PARSER_API_TOKEN");
  if (!baseUrl || !token) return json({ error: "Function secrets are not configured" }, 500);
  const headers = { "X-API-Key": token };

  try {
    const isJson = req.headers.get("content-type")?.includes("application/json");

    if (req.method === "POST" && !isJson) {
      const file = (await req.formData()).get("file");
      if (!(file instanceof File)) return json({ error: "Missing 'file' field" }, 400);
      const name = file.name.toLowerCase();
      if (!ALLOWED.some((ext) => name.endsWith(ext))) {
        return json({ error: `Unsupported file type. Use: ${ALLOWED.join(", ")}` }, 415);
      }
      if (file.size > MAX_BYTES) return json({ error: "File larger than 10 MB" }, 413);

      const body = new FormData();
      body.append("file", file, file.name);
      const upstream = await fetch(`${baseUrl}/parse`, { method: "POST", headers, body });
      return json(await upstream.json(), upstream.status);
    }

    // Status lookup: GET ?job_id=<id>  or  POST application/json { "job_id": "<id>" }
    if (req.method === "GET" || (req.method === "POST" && isJson)) {
      const jobId = req.method === "GET"
        ? new URL(req.url).searchParams.get("job_id")
        : (await req.json().catch(() => ({})))?.job_id;
      if (typeof jobId !== "string" || !/^[a-f0-9]{32}$/.test(jobId)) return json({ error: "Invalid job_id" }, 400);
      const upstream = await fetch(`${baseUrl}/jobs/${jobId}`, { headers });
      return json(await upstream.json(), upstream.status);
    }

    return json({ error: "Method not allowed" }, 405);
  } catch (e) {
    return json({ error: `Upstream request failed: ${e instanceof Error ? e.message : e}` }, 502);
  }
});
