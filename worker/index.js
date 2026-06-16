/**
 * Cloudflare Worker proxy for Bosch Part Queue.
 *
 * Receives part submissions from the PWA, validates them, and writes
 * photo + JSON into the fastcashsignals/bosch-part-queue GitHub repo.
 *
 * Required environment variables:
 *  - GITHUB_TOKEN: fine-grained PAT with read/write Contents on bosch-part-queue
 *  - ALLOWED_ORIGIN: optional, defaults to "https://fastcashsignals.github.io"
 */

const REPO_OWNER = 'fastcashsignals';
const REPO_NAME = 'bosch-part-queue';

function json(body, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...extraHeaders
    }
  });
}

function corsHeaders(request, env) {
  const allowed = env.ALLOWED_ORIGIN || 'https://fastcashsignals.github.io';
  const origin = request.headers.get('Origin') || '';
  const allow = allowed === '*' || origin.startsWith(allowed) ? origin || allowed : allowed;
  return {
    'Access-Control-Allow-Origin': allow,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type'
  };
}

async function githubPut(path, contentBase64, message, env) {
  const url = `https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/contents/${path}`;
  const res = await fetch(url, {
    method: 'PUT',
    headers: {
      'Authorization': `token ${env.GITHUB_TOKEN}`,
      'Accept': 'application/vnd.github+json',
      'Content-Type': 'application/json',
      'X-GitHub-Api-Version': '2022-11-28'
    },
    body: JSON.stringify({ message, content: contentBase64 })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(JSON.stringify({ status: res.status, body: err }));
  }
  return res.json();
}

function slugify(sap) {
  return String(sap).replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 30);
}

function base64Encode(str) {
  // Cloudflare Workers support atob/btoa
  return btoa(unescape(encodeURIComponent(str)));
}

export default {
  async fetch(request, env, ctx) {
    const cors = corsHeaders(request, env);

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: cors });
    }

    if (request.method !== 'POST') {
      return json({ error: 'POST only' }, 405, cors);
    }

    try {
      const body = await request.json();

      const sapId = slugify(body.sap_id);
      const partName = String(body.name || '').trim();
      const costCenter = String(body.cost_center_code || '').trim();
      const bin = String(body.bin || '').trim();
      const category = String(body.category || '').trim();

      if (!sapId || !partName || !costCenter || !bin) {
        return json({ error: 'Missing required fields: sap_id, name, cost_center_code, bin' }, 422, cors);
      }

      if (!body.image_base64) {
        return json({ error: 'Missing image_base64' }, 422, cors);
      }

      const ts = Date.now();
      const stem = `${ts}_${sapId}`;
      const ext = body.image_mime === 'image/png' ? 'png' : 'jpg';
      const imagePath = `submissions/images/${stem}.${ext}`;

      await githubPut(imagePath, body.image_base64, `Photo submission: ${sapId}`, env);

      const record = {
        sap_id: sapId,
        name: partName,
        category: category || costCenter,
        cost_center_code: costCenter,
        bin: bin || null,
        manufacturer: body.manufacturer || null,
        model_number: body.model_number || null,
        description: body.description || null,
        submitted_at: new Date().toISOString(),
        image_path: imagePath
      };

      const jsonPath = `submissions/data/${stem}.json`;
      const jsonContent = base64Encode(JSON.stringify(record, null, 2));
      await githubPut(jsonPath, jsonContent, `Part submission: ${sapId}`, env);

      return json({ success: true, sap_id: sapId, paths: { image: imagePath, data: jsonPath } }, 200, cors);

    } catch (e) {
      return json({ error: e.message || 'Internal error' }, 500, cors);
    }
  }
};
