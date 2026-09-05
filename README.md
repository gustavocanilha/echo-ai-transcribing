# Echo — Transcritor Minimalista de Áudio

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Platform](https://img.shields.io/badge/platform-windows-lightgrey)
![Deps](https://img.shields.io/badge/dependencies-zero-green)
![License](https://img.shields.io/badge/license-a%20definir-yellow)

> Aplicação local ultraleve para transcrição de arquivos de áudio (ex.: `.ogg` do WhatsApp) via APIs de IA. Sem build, sem dependências, sem banco de dados: um único `app.py` servindo UI + backend, com executável Windows de arquivo único (`echo.exe`).

**Destaques de arquitetura**

- **Áudio 100% em memória** — o arquivo é mantido apenas em RAM durante a requisição e descartado após a resposta. Zero persistência de áudio em disco.
- **Bind exclusivo em loopback** — o servidor escuta somente em `127.0.0.1:8080`. Nenhuma exposição em rede local ou internet.
- **Provedor de API flexível** — a chave é fornecida pelo usuário em runtime; o endpoint de transcrição é o da API compatível configurada (padrão: OpenAI `whisper-1`, idioma `pt`).
- **Zero dependências** — apenas biblioteca padrão do Python. Superfície de ataque e custo de manutenção mínimos.

---

## 1. Requisitos de Sistema

| Requisito | Detalhe |
|---|---|
| Linguagem | Python 3.8+ (validado em 3.14) |
| Navegador | Qualquer navegador moderno (Chrome, Edge, Firefox) com suporte a drag-and-drop de arquivos, `fetch` e Clipboard API |
| Chave de API | Chave válida de um provedor de transcrição compatível com a API OpenAI (ex.: OpenAI) |
| SO (dev) | Qualquer SO com Python 3 |
| SO (executável) | Windows 10/11 (para `echo.exe` via `build.bat`) |

---

## 2. Instalação e Execução

### Via executável (Windows)

1. Gere o binário (uma única vez, requer PyInstaller apenas no build):
   ```bat
   build.bat
   ```
2. Execute o artefato gerado:
   ```bat
   dist\echo.exe
   ```
3. O navegador abre automaticamente em `http://127.0.0.1:8080`.

> O `echo.exe` é autocontido (HTML da UI embutido no binário). O único arquivo auxiliar criado em runtime é o `.echo_key` (chave salva, ver §4).

### Instalação manual (qualquer SO)

```bash
# 1. Clonar o repositório
git clone <URL_DO_REPO>

# 2. Entrar no diretório
cd echo

# 3. (Opcional, recomendado) criar e ativar ambiente virtual
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

# 4. Instalar dependências — não há (somente biblioteca padrão)

# 5. Executar a aplicação
python app.py

# 6. Acessar no navegador
# http://127.0.0.1:8080  (abre automaticamente)
```

---

## 3. Como Usar (Guia Passo a Passo)

### 3.1. Configuração da chave de API

1. Cole sua chave no campo **"Chave API OpenAI"** da página.
2. Clique em **"Salvar neste PC"** — a chave é gravada no arquivo `.echo_key`, no mesmo diretório do programa, e reutilizada automaticamente nas próximas execuções (escopo estritamente local; a chave nunca sai da sua máquina exceto nas chamadas autenticadas ao provedor).
3. Alternativa para deploy pré-configurado: preencher a constante `OPENAI_API_KEY` no topo do `app.py`. **Nunca commite uma chave real** (ver §5).

### 3.2. Transcrição de áudio

1. Arraste o arquivo `.ogg` (ex.: baixado do WhatsApp Desktop/Web) para a área de drop — ou clique nela para selecionar o arquivo (formatos aceitos: `.ogg`, `.oga`, `.opus`, `.mp3`, `.m4a`, `.wav`; limite de 25 MB por arquivo, imposto pelo provedor).
2. Clique em **"Transcrever"** e aguarde o processamento.
3. O texto aparece na caixa de resultado — clique em **"Copiar"** para enviá-lo à área de transferência.

### 3.3. Gestão e exclusão de chaves

- **Apagar via interface:** botão **"Apagar salva"** — remove o `.echo_key` e limpa o cache do navegador.
- **Apagar via API:**
  ```bash
  curl -X DELETE http://127.0.0.1:8080/api/key
  ```
- **Verificar se há chave salva (retorna apenas booleano, nunca a chave):**
  ```bash
  curl http://127.0.0.1:8080/api/has-key
  # {"hasKey": true}
  ```

---

## 4. Referência da API Local

Todos os endpoints são servidos em `http://127.0.0.1:8080` (loopback apenas, sem autenticação — por design, como aplicação desktop local single-user).

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/` | UI (página única, HTML servido embutido) |
| `GET` | `/api/has-key` | `{"hasKey": bool}` — indica se há chave disponível (arquivo ou código) |
| `POST` | `/api/key` | Salva a chave em `.echo_key`. Body: `{"key": "sk-..."}` (máx. 1024 bytes) |
| `DELETE` | `/api/key` | Remove a chave salva |
| `POST` | `/api/transcribe` | Transcreve o áudio. Body: bytes brutos do arquivo; headers `Content-Type` (MIME do áudio), `X-Filename` (nome original, URL-encoded), `X-API-Key` (opcional — fallback para chave salva). Resposta: `{"text": "..."}` |

**Prioridade de resolução da chave:** header `X-API-Key` → arquivo `.echo_key` → constante `OPENAI_API_KEY`.

---

## 5. Privacidade, Segurança e LGPD (Conformidade)

- **Finalidade:** transcrição de áudio via provedor de API configurado pelo usuário. O áudio capturado é enviado diretamente ao endpoint da API exclusivamente para transcrição.
- **Retenção de dados:** o áudio é mantido apenas em RAM durante a requisição e descartado imediatamente após a resposta. **Nenhum arquivo de áudio é salvo em disco pelo Echo.**
- **Transferência internacional / terceiros:** o processamento ocorre nos servidores do provedor da API utilizada (ex.: OpenAI nos EUA, ou outro servidor terceiro/local definido pela chave do usuário). **O usuário é responsável por garantir que o provedor escolhido atenda aos seus requisitos de privacidade.**
- **Segurança de chaves:**
  - Chaves **NUNCA** devem ser commitadas no código. A constante `OPENAI_API_KEY` existe apenas para conveniência de deploy pessoal e o próprio código adverte contra o commit.
  - A mecânica recomendada é o botão **"Salvar neste PC"**, que grava a chave em `.echo_key` (texto puro, escopo local).
  - O `.gitignore` do repositório bloqueia `.echo_key`, `.env`, `__pycache__/`, `*.pyc`, `dist/`, `build/` e `*.spec` contra versionamento acidental.
- **Superfície de rede:** bind exclusivo em `127.0.0.1`; nenhuma porta exposta à LAN/internet. A API local não possui autenticação por ser inacessível fora da máquina.

---

## 6. Tratamento de Erros e Troubleshooting

| Sintoma | Causa provável | Resolução |
|---|---|---|
| `401` — "cole sua chave API no campo acima" | Nenhuma chave (digitada, salva ou no código) | Cole a chave na UI e/ou clique em "Salvar neste PC" |
| `400` — Bad Request / Content-Length / JSON inválido | Requisição malformada ao `/api/key` ou `/api/transcribe` | Verifique o payload (`{"key": "..."}`, máx. 1024 bytes) e reenvie pela UI |
| `400` — "arquivo maior que 25 MB" | Limite do provedor de transcrição | Comprima/divida o áudio e tente novamente |
| `502` — falha de comunicação com a API | Chave inválida/expirada, sem rede, cota excedida ou instabilidade no provedor | Valide a chave no painel do provedor, cheque a conexão e a cota; tente de novo |
| Timeout / socket (60 s) | Conexão interrompida antes da leitura completa do payload | Reenvie o arquivo; se persistir, verifique proxy/antivírus local |
| Navegador não abre sozinho | Ambiente sem browser padrão / execução headless | Acesse manualmente `http://127.0.0.1:8080` |
| Porta `8080` em uso | Outra instância do Echo (ou app) rodando | Encerre a outra instância (`Ctrl+C`) e reinicie |
| Botão "Copiar" não funciona | Permissão de clipboard negada (contexto não-seguro) | O app usa fallback automático de cópia; como servido via `localhost` (contexto seguro), permita clipboard nas configurações do site se necessário |

---

## 7. Estrutura do Repositório

```text
echo/
├── app.py          # Servidor HTTP (stdlib) + UI embutida + integração com a API de transcrição
├── build.bat       # Build do executável Windows de arquivo único (PyInstaller)
├── .gitignore      # Protege .echo_key, .env, dist/, build/, __pycache__/ etc.
└── README.md       # Este arquivo
```

Artefatos criados **em runtime** (não versionados):

```text
.echo_key           # Chave de API salva via "Salvar neste PC" (texto puro, escopo local)
dist/echo.exe       # Binário Windows gerado pelo build.bat
```

---

## 8. Desenvolvimento

```bash
python app.py   # sem dependências; apenas biblioteca padrão
```

- Convenção: manter `app.py` em arquivo único e sem dependências externas (requisito de portabilidade do `echo.exe`).
- Antes do `push`: garanta que nenhuma chave real esteja em `app.py` ou `.echo_key`, e rode o fluxo completo (salvar → transcrever → apagar).

## 9. Licença

Repositório sem arquivo `LICENSE` no momento — recomenda-se adotar uma licença explícita (ex.: MIT) antes da distribuição pública.
