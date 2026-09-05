#!/usr/bin/env python3
"""Echo - transcritor minimalista de audio (WhatsApp .ogg -> texto).

Uso dev:    python app.py
Uso final:  echo.exe  (gera via build.bat) -> abre http://localhost:8080

Somente biblioteca padrao. Sem pip install.
"""

import http.server
import base64
import json
import mimetypes
import os
import sys
import threading
import urllib.request
import urllib.error
import webbrowser

# ============================================================
#  PROVEDORES SUPORTADOS: "gemini" (Google, com nivel gratuito)
#  e "openai" (OpenAI, pago). PROVIDER abaixo e apenas o padrao
#  inicial — o provedor pode ser trocado a qualquer momento na UI.
#  (Anthropic ainda nao oferece transcricao de audio na API publica.)
# ============================================================
PROVIDERS = ("gemini", "openai")
PROVIDER = "gemini"

#  CHAVES PRE-SALVAS (opcional, uma por provedor).
#  NUNCA commite chaves reais neste arquivo. Utilize o recurso
#  'Salvar neste PC' da UI (grava num arquivo .echo_key ao lado
#  do app.py / echo.exe e nunca pede de novo).
GEMINI_API_KEY = ""
OPENAI_API_KEY = ""


def _base_dir():
    # Ao lado do echo.exe quando compilado, ao lado do app.py em dev
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


KEY_FILE = os.path.join(_base_dir(), ".echo_key")


def load_store():
    """Le o .echo_key: {"provider": ..., "keys": {"gemini": ..., "openai": ...}}."""
    store = {"provider": "", "keys": {}}
    try:
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            raw = f.read().strip()
    except OSError:
        return store
    if not raw:
        return store
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    if isinstance(data, dict):
        keys = data.get("keys")
        if isinstance(keys, dict):
            for p in PROVIDERS:
                v = keys.get(p)
                if isinstance(v, str) and v.strip():
                    store["keys"][p] = v.strip()
        if data.get("provider") in PROVIDERS:
            store["provider"] = data["provider"]
        return store
    # legado: versoes antigas gravavam a chave em texto puro
    if raw.startswith("AIza"):
        store["keys"]["gemini"] = raw
    elif raw.startswith("sk-"):
        store["keys"]["openai"] = raw
    else:
        store["keys"][PROVIDER] = raw
    return store


def save_store(provider, key):
    store = load_store()
    store["keys"][provider] = key.strip()
    store["provider"] = provider
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f)
    try:
        os.chmod(KEY_FILE, 0o600)  # leitura/escrita so p/ o dono (best-effort no Windows)
    except OSError:
        pass


def delete_store():
    try:
        os.remove(KEY_FILE)
        return True
    except OSError:
        return False


def resolve_key(provider, header_key):
    """Chave efetiva: header > arquivo salvo > constante do provedor."""
    if header_key:
        return header_key
    store = load_store()
    if store["keys"].get(provider):
        return store["keys"][provider]
    if provider == "gemini" and GEMINI_API_KEY:
        return GEMINI_API_KEY
    if provider == "openai" and OPENAI_API_KEY:
        return OPENAI_API_KEY
    return ""

PORT = 8080
OPENAI_MODEL = "whisper-1"  # OpenAI: barato e otimo para PT
GEMINI_MODEL = "gemini-3.6-flash"  # Gemini: rapido, com nivel gratis
MAX_BYTES = {  # limite de audio por provedor
    "openai": 25 * 1024 * 1024,
    "gemini": 20 * 1024 * 1024,  # limite do Gemini p/ audio inline
}


HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Echo - Transcrever</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, sans-serif; max-width: 560px; margin: 40px auto; padding: 0 16px; color: #111; }
  h1 { font-size: 22px; margin-bottom: 4px; }
  p.sub { color: #666; font-size: 14px; margin-top: 0; }
  label { display: block; font-size: 13px; margin: 16px 0 4px; color: #333; }
  input[type=password], input[type=text], select { width: 100%; padding: 10px; font-size: 14px; border: 1px solid #ccc; border-radius: 8px; background: #fff; }
  #drop { border: 2px dashed #bbb; border-radius: 12px; padding: 28px 16px; text-align: center; color: #555; font-size: 14px; cursor: pointer; margin-top: 4px; }
  #drop.over { border-color: #111; background: #f6f6f6; }
  #drop b { display: block; font-size: 15px; color: #111; margin-bottom: 4px; }
  button { width: 100%; padding: 12px; font-size: 15px; border: 0; border-radius: 8px; cursor: pointer; margin-top: 12px; }
  .row { display: flex; gap: 8px; }
  .row button { width: auto; flex: 1; padding: 8px; font-size: 13px; margin-top: 8px; background: #eee; color: #111; }
  #btnGo { background: #111; color: #fff; }
  #btnGo:disabled { background: #999; cursor: wait; }
  #btnCopy { background: #eee; color: #111; display: none; }
  #status { font-size: 13px; color: #666; margin-top: 10px; min-height: 18px; }
  #out { width: 100%; min-height: 160px; margin-top: 8px; padding: 10px; font-size: 14px; border: 1px solid #ccc; border-radius: 8px; display: none; resize: none; overflow: hidden; }
  .hint { font-size: 12px; color: #888; margin-top: 16px; }
  .privacy { font-size: 12px; color: #555; background: #f6f6f6; border-radius: 8px; padding: 8px 10px; margin-top: 12px; }
</style>
</head>
<body>
  <h1>Echo</h1>
  <p class="sub">Arraste o .ogg do WhatsApp, transcreva, copie.</p>
  <p class="privacy">O &aacute;udio capturado &eacute; enviado diretamente para a API do provedor selecionado abaixo, exclusivamente para transcri&ccedil;&atilde;o. Nenhum dado &eacute; armazenado localmente.</p>

  <label for="provider">Provedor</label>
  <select id="provider">
    <option value="gemini">Google Gemini</option>
    <option value="openai">OpenAI</option>
  </select>

  <label for="key">Chave de API</label>
  <input type="password" id="key" placeholder="" autocomplete="off">
  <div class="row">
    <button id="btnSave">Salvar neste PC</button>
    <button id="btnForget">Apagar salvas</button>
  </div>
  <div class="hint" id="keyHint"></div>

  <label>Arquivo de &aacute;udio</label>
  <div id="drop">
    <b id="dropTitle">Arraste o .ogg aqui</b>
    <span>ou clique para escolher</span>
    <input type="file" id="file" accept=".ogg,.oga,.opus,.mp3,.m4a,.wav,audio/*" hidden>
  </div>

  <button id="btnGo">Transcrever</button>
  <div id="status"></div>
  <textarea id="out" readonly placeholder="Transcri&ccedil;&atilde;o aparece aqui..."></textarea>
  <button id="btnCopy">Copiar</button>

<script>
const $ = id => document.getElementById(id);
const key = $('key'), fileInput = $('file'), drop = $('drop'),
      dropTitle = $('dropTitle'), btnGo = $('btnGo'),
      btnCopy = $('btnCopy'), out = $('out'), status = $('status'),
      provSel = $('provider');

const PROVIDERS = {
  gemini: { name: 'Google Gemini', placeholder: 'AIza...', keyUrl: 'https://aistudio.google.com/apikey', keyUrlText: 'Google AI Studio' },
  openai: { name: 'OpenAI', placeholder: 'sk-...', keyUrl: 'https://platform.openai.com/api-keys', keyUrlText: 'plataforma OpenAI' }
};

// provedor + chaves no navegador (uma chave por provedor)
// a escolha explicita do usuario nunca e sobrescrita pelo servidor
let userPickedProvider = !!localStorage.getItem('echo_provider');
provSel.value = localStorage.getItem('echo_provider') || 'gemini';
function browserKey(p) { return localStorage.getItem('echo_key_' + p) || ''; }
function refreshKeyField() { key.value = browserKey(provSel.value); }
provSel.addEventListener('change', () => {
  localStorage.setItem('echo_provider', provSel.value);
  userPickedProvider = true;
  refreshKeyField();
  updateKeyUI();
});
key.addEventListener('input', () => {
  localStorage.setItem('echo_key_' + provSel.value, key.value.trim());
});
refreshKeyField();

// status das chaves salvas no servidor (por provedor)
let serverStatus = { provider: 'gemini', hasKey: {} };
function updateKeyUI() {
  const p = provSel.value, info = PROVIDERS[p];
  key.placeholder = info.placeholder;
  const saved = serverStatus.hasKey && serverStatus.hasKey[p];
  document.getElementById('keyHint').innerHTML =
    (saved ? 'Chave de ' + info.name + ' salva neste PC. Pode deixar em branco.<br>' : '') +
    'Obter chave em: <a href="' + info.keyUrl + '" target="_blank" rel="noopener">' + info.keyUrlText + '</a>';
}
function refreshKeyHint() {
  fetch('/api/has-key').then(r => r.json()).then(d => {
    serverStatus = d;
    if (!userPickedProvider && d.provider && PROVIDERS[d.provider]) {
      provSel.value = d.provider;
      localStorage.setItem('echo_provider', d.provider);
      refreshKeyField();
    }
    updateKeyUI();
  }).catch(() => updateKeyUI());
}
refreshKeyHint();

$('btnSave').addEventListener('click', async () => {
  const k = key.value.trim();
  if (!k) { status.textContent = 'Cole a chave no campo antes de salvar.'; return; }
  const res = await fetch('/api/key', { method: 'POST', body: JSON.stringify({ provider: provSel.value, key: k }) });
  if (res.ok) { status.textContent = 'Chave de ' + PROVIDERS[provSel.value].name + ' salva neste PC.'; refreshKeyHint(); }
  else status.textContent = 'Erro ao salvar chave.';
});

$('btnForget').addEventListener('click', async () => {
  await fetch('/api/key', { method: 'DELETE' });
  key.value = '';
  localStorage.removeItem('echo_key_gemini');
  localStorage.removeItem('echo_key_openai');
  localStorage.removeItem('echo_api_key');
  localStorage.removeItem('openai_key');
  status.textContent = 'Chaves apagadas.';
  refreshKeyHint();
});

let file = null;
function setFile(f) {
  file = f;
  if (f) dropTitle.textContent = '📎 ' + f.name + ' (' + (f.size/1024).toFixed(0) + ' KB)';
}
drop.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', e => setFile(e.target.files[0]));
['dragover','dragenter'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
['dragleave','drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
drop.addEventListener('drop', e => { if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]); });

btnGo.addEventListener('click', async () => {
  if (!file) { status.textContent = 'Escolha um arquivo .ogg primeiro.'; return; }
  btnGo.disabled = true;
  btnCopy.style.display = 'none';
  out.style.display = 'none';
  status.textContent = 'Transcrevendo... aguarde.';
  try {
    const res = await fetch('/api/transcribe', {
      method: 'POST',
      headers: {
        'Content-Type': file.type || 'audio/ogg',
        'X-Filename': encodeURIComponent(file.name),
        'X-Provider': provSel.value,
        'X-API-Key': key.value.trim()
      },
      body: file
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ('Erro ' + res.status));
    out.value = data.text || '';
    out.style.height = 'auto';
    out.style.height = out.scrollHeight + 'px';
    out.style.display = 'block';
    btnCopy.style.display = 'block';
    status.textContent = 'Pronto.';
  } catch (err) {
    status.textContent = 'Erro: ' + err.message;
  } finally {
    btnGo.disabled = false;
  }
});

btnCopy.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(out.value);
    btnCopy.textContent = 'Copiado!';
  } catch {
    out.select();
    document.execCommand('copy');
    btnCopy.textContent = 'Copiado!';
  }
  setTimeout(() => btnCopy.textContent = 'Copiar', 1500);
});
</script>
</body>
</html>
"""


def transcribe_openai(audio_bytes: bytes, filename: str, api_key: str) -> str:
    """Envia o audio para a API OpenAI e retorna o texto."""
    boundary = "----EchoBoundary7MA4YWxkTrZu0GgW"
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "ogg").lower() or "ogg"
    mime = mimetypes.guess_type("f." + ext)[0] or "audio/ogg"

    def field(name, value):
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()

    body = b""
    body += field("model", OPENAI_MODEL)
    body += field("language", "pt")
    body += field("response_format", "json")
    body += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode()
    body += audio_bytes + b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("text", "")
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8", "ignore"))
            msg = err.get("error", {}).get("message", str(err))
        except Exception:
            msg = f"HTTP {e.code}"
        raise RuntimeError(msg)


def transcribe_gemini(audio_bytes: bytes, mime_type: str, api_key: str) -> str:
    """Envia o audio ao Gemini (generateContent, audio inline) e retorna o texto."""
    payload = json.dumps({
        "contents": [{
            "parts": [
                {"text": "Transcreva este audio na integra, em portugues, sem comentarios adicionais. Retorne apenas a transcricao."},
                {"inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(audio_bytes).decode("ascii"),
                }},
            ]
        }],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 16384},
    }).encode("utf-8")

    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        data=payload,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8", "ignore"))
            msg = err.get("error", {}).get("message", str(err))
        except Exception:
            msg = f"HTTP {e.code}"
        raise RuntimeError(msg)
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))
        raise RuntimeError("resposta inesperada do provedor")


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "Echo/1.0"

    def _json(self, obj, code=200):
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            raw = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        elif self.path == "/api/has-key":
            store = load_store()
            provider = store["provider"] or PROVIDER
            if provider not in PROVIDERS:
                provider = PROVIDER
            status = {}
            for p in PROVIDERS:
                const = GEMINI_API_KEY if p == "gemini" else OPENAI_API_KEY
                status[p] = bool(store["keys"].get(p) or const)
            self._json({"provider": provider, "hasKey": status})
        else:
            self._json({"error": "nao encontrado"}, 404)

    def do_POST(self):
        if self.path == "/api/key":
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (ValueError, TypeError):
                return self._json({"error": "chave invalida"}, 400)
            if length <= 0 or length > 1024:
                return self._json({"error": "chave invalida"}, 400)
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(data, dict):
                    return self._json({"error": "chave invalida"}, 400)
                prov = (data.get("provider") or "").strip().lower()
                k = (data.get("key") or "").strip()
            except Exception:
                return self._json({"error": "chave invalida"}, 400)
            if prov not in PROVIDERS or not k or len(k) > 512:
                return self._json({"error": "chave invalida"}, 400)
            try:
                save_store(prov, k)
            except OSError as e:
                return self._json({"error": f"nao consegui salvar: {e}"}, 500)
            return self._json({"ok": True})

        if self.path != "/api/transcribe":
            return self._json({"error": "nao encontrado"}, 404)

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (ValueError, TypeError):
            return self._json({"error": "tamanho do arquivo invalido"}, 400)
        if length <= 0:
            return self._json({"error": "arquivo vazio"}, 400)
        provider = (self.headers.get("X-Provider") or "").strip().lower()
        if not provider:
            provider = load_store()["provider"] or PROVIDER
        if provider not in PROVIDERS:
            return self._json({"error": "provedor invalido (use: gemini, openai)"}, 400)
        limit = MAX_BYTES[provider]
        if length > limit:
            return self._json({"error": f"arquivo maior que {limit // (1024 * 1024)} MB (limite do provedor)"}, 400)

        api_key = resolve_key(provider, (self.headers.get("X-API-Key") or "").strip())
        if not api_key:
            return self._json({"error": "cole sua chave de API no campo acima"}, 401)

        filename = self.headers.get("X-Filename") or "audio.ogg"
        try:
            from urllib.parse import unquote
            filename = unquote(filename)
        except Exception:
            filename = "audio.ogg"
        filename = filename.replace("\r", "").replace("\n", "").replace('"', "").replace(";", "")[:120] or "audio.ogg"

        audio = self.rfile.read(length)
        try:
            if provider == "gemini":
                ext = (filename.rsplit(".", 1)[-1] if "." in filename else "ogg").lower() or "ogg"
                mime = mimetypes.guess_type("f." + ext)[0] or "audio/ogg"
                text = transcribe_gemini(audio, mime, api_key)
            else:
                text = transcribe_openai(audio, filename, api_key)
        except RuntimeError as e:
            return self._json({"error": str(e)}, 502)
        except Exception as e:  # noqa: BLE001 - erro generico vira msg simples
            return self._json({"error": f"falha interna: {e}"}, 500)
        self._json({"text": text})

    def do_DELETE(self):
        if self.path == "/api/key":
            delete_store()
            return self._json({"ok": True})
        return self._json({"error": "nao encontrado"}, 404)

    def log_message(self, fmt, *args):
        pass  # silencioso de proposito


def main():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.socket.settimeout(60)  # evita thread presa em leitura incompleta
    url = f"http://localhost:{PORT}"
    print(f"Echo rodando em {url}")
    print("Pressione Ctrl+C para encerrar.")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
