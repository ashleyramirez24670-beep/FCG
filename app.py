from flask import Flask, render_template_string, request, jsonify, Response
import requests

app = Flask(__name__)

# If you want to force API requests through the server instead of directly from the browser,
# set USE_PROXY = True. Be aware this will require CORS handling and user's cookies won't
# automatically be forwarded (unless you implement cookie forwarding/auth). By default we let
# the browser call fraud.cat directly.
USE_PROXY = False
FRAUD_BASE = "https://fraud.cat"

# The HTML template: includes CSS (from styles.css you provided) and JS (adapted from popup.js)
HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>FraudCat Codes</title>
  <style>
    body {
      font-family: Arial;
      width: 300px;
      padding: 10px;
      background: #111;
      color: white;
    }

    input {
      width: 100%;
      margin-bottom: 8px;
      padding: 8px;
    }

    button {
      width: 100%;
      padding: 10px;
      background: #00c853;
      border: none;
      color: white;
      cursor: pointer;
    }

    #output {
      margin-top: 10px;
      max-height: 300px;
      overflow-y: auto;
    }

    hr {
      border: none;
      border-top: 1px solid #222;
      margin: 8px 0;
    }
  </style>
</head>
<body>
  <h3>FraudCat Codes</h3>
  <input id="email" placeholder="example@fraud.cat" />
  <button id="start">Get Codes</button>
  <div id="output"></div>

  <script>
  (function() {
    const BASE = "{{ base_url }}";
    const USE_PROXY = {{ use_proxy|lower }};
    const output = document.getElementById("output");

    // store seen identifiers so we only append new codes
    const seenMessages = new Set(); // stores uid or generated id for messages
    const seenCodesPerMessage = new Map(); // messageId -> Set of codes already shown

    function extractCodes(text) {
      return text.match(/\\b\\d{4,8}\\b/g) || [];
    }

    function parseEmail(email) {
      const parts = email.split("@");
      return { address: parts[0], domain: parts[1] };
    }

    async function fetchViaProxy(path, body) {
      // Proxy endpoint on this server: /proxy which will forward to FRAUD_BASE.
      // Only used if USE_PROXY is true (see server config).
      try {
        const res = await fetch('/proxy', {
          method: 'POST',
          headers: { 'content-type': 'application/json;charset=UTF-8' },
          body: JSON.stringify({ path, body })
        });
        if (!res.ok) throw new Error('Proxy error: ' + res.status);
        return await res.json();
      } catch (e) {
        console.error('Proxy fetch error', e);
        throw e;
      }
    }

    async function getInbox(toAddress, toDomain) {
      const path = "/api/services/app/mail/GetInbox";
      const payload = { toAddress, toDomain };

      if (USE_PROXY) {
        const res = await fetchViaProxy(path, payload);
        return res.result?.emails || [];
      }

      const res = await fetch(BASE + path, {
        method: "POST",
        credentials: "include",
        headers: {
          "content-type": "application/json;charset=UTF-8"
        },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      return data.result?.emails || [];
    }

    async function getEmail(uid) {
      const path = "/api/services/app/mail/GetLetterById";
      const payload = { uid };

      if (USE_PROXY) {
        const res = await fetchViaProxy(path, payload);
        return res.result || null;
      }

      const res = await fetch(BASE + path, {
        method: "POST",
        credentials: "include",
        headers: {
          "content-type": "application/json;charset=UTF-8"
        },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      return data.result || null;
    }

    // generate an id for messages that don't have a uid to help dedupe
    function generateIdForMessage(msg) {
      if (msg.uid) return String(msg.uid);
      // fallback: use subject + a short snippet of body/content
      const snippet = (msg.body || msg.content || msg.htmlBody || msg.textBody || "").slice(0, 120);
      return `no-uid:${(msg.subject || "no-subject")}|${snippet}`;
    }

    function appendNewCodesToOutput(messageId, subject, newCodes) {
      if (!newCodes || newCodes.length === 0) return;
      const container = document.createElement("div");
      const subj = document.createElement("b");
      subj.textContent = subject || "No subject";
      const codesText = document.createElement("div");
      codesText.textContent = `Codes: ${newCodes.join(", ")}`;
      const hr = document.createElement("hr");

      container.appendChild(subj);
      container.appendChild(document.createElement("br"));
      container.appendChild(codesText);
      container.appendChild(hr);

      output.appendChild(container);
      // scroll to bottom so new codes are visible
      output.scrollTop = output.scrollHeight;
    }

    async function processMessage(msg) {
      const messageId = generateIdForMessage(msg);

      // fetch full email if needed
      let full = msg;
      if (msg.uid) {
        try {
          full = await getEmail(msg.uid) || msg;
        } catch (e) {
          // on error, keep using provided msg
          full = msg;
        }
      }

      const body =
        full.body ||
        full.content ||
        full.htmlBody ||
        full.textBody ||
        "";

      const codes = extractCodes(body);

      if (!codes.length) {
        // mark message as seen so we don't refetch forever (optional)
        if (!seenMessages.has(messageId)) {
          seenMessages.add(messageId);
          seenCodesPerMessage.set(messageId, new Set());
        }
        return;
      }

      // get set of previously seen codes for this message
      const seenSet = seenCodesPerMessage.get(messageId) || new Set();
      const newlyFound = [];

      for (const c of codes) {
        if (!seenSet.has(c)) {
          newlyFound.push(c);
          seenSet.add(c);
        }
      }

      // store updated seen codes and mark message seen
      seenCodesPerMessage.set(messageId, seenSet);
      seenMessages.add(messageId);

      if (newlyFound.length) {
        appendNewCodesToOutput(messageId, msg.subject || "No subject", newlyFound);
      }
    }

    async function fetchNewCodes(email) {
      const { address, domain } = parseEmail(email);
      const inbox = await getInbox(address, domain);

      // process each message but do not clear output
      for (let msg of inbox) {
        const messageId = generateIdForMessage(msg);

        if (seenMessages.has(messageId) && !msg.uid) {
          // already processed and cannot fetch more detail -> skip
          continue;
        }

        try {
          await processMessage(msg);
        } catch (e) {
          console.error("Error processing message", e);
        }
      }
    }

    let pollingHandle = null;

    document.getElementById("start").onclick = async () => {
      const email = document.getElementById("email").value.trim();
      if (!email) return;

      // clear any previous error text but DO NOT clear output
      output.innerHTML = output.innerHTML || "";

      try {
        await fetchNewCodes(email);
      } catch (e) {
        output.innerHTML = "Error: Make sure you're logged into FraudCat or enable server proxy.";
      }

      // clear existing interval if any and set new 10s interval
      if (pollingHandle) clearInterval(pollingHandle);
      pollingHandle = setInterval(() => {
        const emailNow = document.getElementById("email").value.trim();
        if (emailNow) fetchNewCodes(emailNow);
      }, 10000); // 10 seconds
    };
  })();
  </script>
</body>
</html>
"""

@app.route("/")
def index():
    # serve page, pass base url and flag to toggle proxy usage in client-side JS
    return render_template_string(HTML_TEMPLATE, base_url=FRAUD_BASE, use_proxy=USE_PROXY)

# Optional proxy route: forwards POST requests for the FraudCat API.
# NOTE: This is provided only as an example. Using it in production needs careful
# consideration: authentication, cookies, rate limits, CORS, TLS, and security.
@app.route("/proxy", methods=["POST"])
def proxy():
    if not USE_PROXY:
        return jsonify({"error": "Proxy disabled"}), 403

    payload = request.get_json() or {}
    path = payload.get("path")
    body = payload.get("body", {})

    if not path:
        return jsonify({"error": "Missing path"}), 400

    url = FRAUD_BASE.rstrip("/") + path
    try:
        # Forward request. Cookies from user's browser won't be forwarded.
        # If you need to forward cookies, you'd have to accept them from client
        # and attach them here (with appropriate security measures).
        r = requests.post(url, json=body, timeout=10)
        return Response(r.content, status=r.status_code, content_type=r.headers.get('Content-Type', 'application/json'))
    except Exception as e:
        return jsonify({"error": "Backend proxy failed", "detail": str(e)}), 500

if __name__ == "__main__":
    # To run locally:
    # pip install flask requests
    # FLASK_APP=app.py flask run --host=0.0.0.0 --port=5000
    #
    # Or run directly:
    app.run(host="0.0.0.0", port=5000, debug=True)
