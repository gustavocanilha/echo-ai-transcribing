#!/usr/bin/env python3
"""Echo - transcritor minimalista de audio (WhatsApp .ogg -> texto).

Uso dev:    python app.py
Uso final:  echo.exe  (gera via build.bat) -> abre http://localhost:8080

Somente biblioteca padrao. Sem pip install.
"""

import http.server
import json
import mimetypes
import os
import sys
import threading
import urllib.request
import urllib.error
import webbrowser

# ============================================================
#  COLE SUA CHAVE AQUI PARA DEIXAR PRE-SALVA AO INICIAR:
#  Ex: OPENAI_API_KEY = "sk-..."
#  NUNCA commite sua chave real neste arquivo. Utilize o
#  recurso 'Salvar neste PC' da UI (grava num arquivo
#  .echo_key ao lado do app.py / echo.exe e nunca pede de novo).
# ============================================================
OPENAI_API_KEY = ""


def _base_dir():
    # Ao lado do echo.exe quando compilado, ao lado do app.py em dev
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


KEY_FILE = os.path.join(_base_dir(), ".echo_key")


def load_saved_key():
    try:
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def save_key_to_disk(key):
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key.strip())


def delete_saved_key():
    try:
        os.remove(KEY_FILE)
        return True
    except OSError:
        return False


def server_has_key():
    return bool(load_saved_key() or OPENAI_API_KEY)

PORT = 8080
MODEL = "whisper-1"  # barato e otimo para PT
MAX_BYTES = 25 * 1024 * 1024  # limite da API OpenAI


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
  input[type=password], input[type=text] { width: 100%; padding: 10px; font-size: 14px; border: 1px solid #ccc; border-radius: 8px; }
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
  #out { width: 100%; min-height: 160px; margin-top: 8px; padding: 10px; font-size: 14px; border: 1px solid #ccc; border-radius: 8px; display: none; }
  .hint { font-size: 12px; color: #888; margin-top: 16px; }
  .privacy { font-size: 12px; color: #555; background: #f6f6f6; border-radius: 8px; padding: 8px 10px; margin-top: 12px; }
</style>
</head>
<body>
  <h1>Echo</h1>
  <p class="sub">Arraste o .ogg do WhatsApp, transcreva, copie.</p>
  <p class="privacy">O &aacute;udio capturado &eacute; enviado diretamente para a API do provedor configurado (ex.: OpenAI) exclusivamente para transcri&ccedil;&atilde;o. Nenhum dado &eacute; armazenado localmente.</p>

  <label for="key">Chave API OpenAI</label>
  <input type="password" id="key" placeholder="sk-..." autocomplete="off">
  <div class="row">
    <button id="btnSave">Salvar neste PC</button>
    <button id="btnForget">Apagar salva</button>
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
      btnCopy = $('btnCopy'), out = $('out'), status = $('status');

// chave salva no navegador
key.value = localStorage.getItem('openai_key') || '';
key.addEventListener('input', () => {
  localStorage.setItem('openai_key', key.value.trim());
});

// avisa se o servidor ja tem chave salva
function refreshKeyHint() {
  fetch('/api/has-key').then(r => r.json()).then(d => {
    document.getElementById('keyHint').textContent = d.hasKey
      ? 'Chave salva neste PC. Pode deixar em branco.'
      : 'Cole a chave uma vez e clique em "Salvar neste PC".';
  }).catch(() => {});
}
refreshKeyHint();

$('btnSave').addEventListener('click', async () => {
  const k = key.value.trim();
  if (!k) { status.textContent = 'Cole a chave no campo antes de salvar.'; return; }
  const res = await fetch('/api/key', { method: 'POST', body: JSON.stringify({ key: k }) });
  if (res.ok) { status.textContent = 'Chave salva neste PC.'; refreshKeyHint(); }
  else status.textContent = 'Erro ao salvar chave.';
});

$('btnForget').addEventListener('click', async () => {
  await fetch('/api/key', { method: 'DELETE' });
  key.value = '';
  localStorage.removeItem('openai_key');
  status.textContent = 'Chave apagada.';
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
        'X-API-Key': key.value.trim()
      },
      body: file
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ('Erro ' + res.status));
    out.value = data.text || '';
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
    body += field("model", MODEL)
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
            self._json({"hasKey": server_has_key()})
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
                k = (data.get("key") or "").strip()
            except Exception:
                return self._json({"error": "chave invalida"}, 400)
            if not k or len(k) > 512:
                return self._json({"error": "chave invalida"}, 400)
            try:
                save_key_to_disk(k)
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
        if length > MAX_BYTES:
            return self._json({"error": "arquivo maior que 25 MB (limite da API)"}, 400)

        api_key = (self.headers.get("X-API-Key") or "").strip() or load_saved_key() or OPENAI_API_KEY
        if not api_key:
            return self._json({"error": "cole sua chave API no campo acima"}, 401)

        filename = self.headers.get("X-Filename") or "audio.ogg"
        try:
            from urllib.parse import unquote
            filename = unquote(filename)
        except Exception:
            filename = "audio.ogg"
        filename = filename.replace("\r", "").replace("\n", "").replace('"', "").replace(";", "")[:120] or "audio.ogg"

        audio = self.rfile.read(length)
        try:
            text = transcribe_openai(audio, filename, api_key)
        except RuntimeError as e:
            return self._json({"error": str(e)}, 502)
        except Exception as e:  # noqa: BLE001 - erro generico vira msg simples
            return self._json({"error": f"falha interna: {e}"}, 500)
        self._json({"text": text})

    def do_DELETE(self):
        if self.path == "/api/key":
            delete_saved_key()
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
