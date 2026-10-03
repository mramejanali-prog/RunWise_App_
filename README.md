# RunWise 1.0.0 — release candidate

Aplicação Android + API FastAPI para gestão de treino de corrida.

## Incluído

- Registo/login com JWT.
- Histórico de atividades e sincronização cloud.
- Health Connect para sessões de corrida.
- Separação entre treino normal e prova oficial.
- Objetivos pessoais.
- Motor de treinador adaptativo.
- Plano semanal persistido localmente e na cloud.
- Estado de treino planeado: concluído/pulado.
- Relatórios semanal, quinzenal, mensal, trimestral, semestral e anual.
- Exportação dos treinos para o calendário Android.
- Motivação diária por notificação.
- Biblioteca de técnicas de corrida.
- Persistência cloud das provas por utilizador.
- Contrato de ingestão preparado para TCHACO.

## Backend

```bash
cd backend
python -m venv .venv
# ativar ambiente virtual
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Variáveis importantes:

- `DATABASE_URL` — PostgreSQL em produção; SQLite pode ser usado para desenvolvimento.
- `JWT_SECRET` — segredo forte e privado em produção.
- `JWT_EXPIRE_MINUTES` — validade do token.

## Android

Abrir `android/` no Android Studio e configurar SDK/Gradle. O endpoint padrão no emulador é `http://10.0.2.2:8000`.

A sincronização periódica é feita pelo WorkManager quando existe conectividade.

## Endpoints principais v0.8

- `POST /v1/auth/register`
- `POST /v1/auth/login`
- `GET /v1/me`
- `POST/GET /v1/sync/activities`
- `POST/GET /v1/sync/goals`
- `POST/GET /v1/sync/races`
- `POST/GET /v1/sync/planned-workouts`
- `POST /v1/coach/plan`
- `POST /v1/coach/adjust`
- `POST /v1/integrations/tchaco/races`
- `GET /v1/motivation/today`

## v0.11 — sincronização incremental e migrações

- Alembic + migração versionada para `updated_at`.
- Sync incremental por cursor para atividades, objetivos, provas e treinos planeados.
- O servidor só altera `updated_at` quando existe alteração real.
- Integração Google Calendar OAuth.
- Integração TCHACO mediante API oficial/credenciais.
- CI para testes backend e build Android.

## Limitações conhecidas

- A resolução de conflitos offline ainda usa o último estado recebido/enviado; a próxima camada será uma política explícita de conflitos por timestamp/versão.
- Google Calendar OAuth ainda requer credenciais OAuth do projeto.
- TCHACO continua dependente de API oficial/credenciais de integração; o endpoint de ingestão já está preparado, mas não finge uma ligação automática que ainda não existe.
- O APK/AAB não é gerado neste ambiente porque não há Android SDK/Gradle disponível.


## v0.11 — sincronização segura entre dispositivos
- Sincronização incremental mantém cursores por entidade.
- Escritas enviam `base_since` para concorrência otimista.
- Se um registo remoto mudou depois do cursor conhecido pelo dispositivo, a escrita local é rejeitada apenas nesse registo; a leitura incremental recupera a versão remota.
- Os cursores de sincronização são limpos ao iniciar uma nova sessão ou terminar sessão, evitando mistura de dados entre contas.
- A API devolve `conflicts` nos endpoints de sincronização para permitir telemetria e tratamento futuro explícito.

Limitação: o cliente Android atualmente adota a versão remota em caso de conflito. Não há ainda uma interface de resolução manual campo-a-campo.


### Produção v0.11
Defina `APP_ENV=production`, `DATABASE_URL` PostgreSQL e um `JWT_SECRET` aleatório com pelo menos 32 caracteres. Configure `CORS_ORIGINS` e `ALLOWED_HOSTS` conforme o domínio de produção. O rate limiting padrão é 120 pedidos/minuto por IP e 10 pedidos/5 minutos para endpoints de autenticação.

### Google Calendar
O Android usa o `CalendarContract` do sistema. Quando existem vários calendários graváveis, o RunWise prioriza um calendário com `ACCOUNT_TYPE=com.google`; caso não exista, usa o primeiro calendário gravável visível. Assim, o utilizador pode usar a conta Google já configurada no telefone sem colocar credenciais Google dentro da aplicação.


### TCHACO integration
The backend supports a signed webhook boundary for an authorized TCHACO integration. Configure `TCHACO_WEBHOOK_SECRET` and send `X-TCHACO-Signature` as HMAC-SHA256 of the raw JSON body. No scraping or undocumented endpoint is used.

## Release build v0.27
1. Copy `android/keystore.properties.example` to `android/keystore.properties`.
2. Fill the path/passwords for a release keystore. Never commit this file or the keystore.
3. With Android SDK/Gradle installed, run `./gradlew :app:assembleRelease` for APK or `./gradlew :app:bundleRelease` for AAB.
4. The current development environment does not contain the Android SDK/Gradle toolchain, so the release artifact cannot be compiled here.


## v0.17 — sincronização offline e conflitos

- Fila persistente `sync_queue` em Room para alterações locais.
- Operações são reenviadas pelo WorkManager quando existe conectividade.
- Retry com backoff exponencial.
- A API devolve IDs em conflito; esses itens ficam marcados como `CONFLICT` e não são apagados silenciosamente.
- A migração Room 3→4 cria a fila sem apagar dados.
- Instalações antigas v1/v2 mantêm o fallback histórico; versões v3+ usam a migração explícita.
- Sincronização manual inclui também os treinos planeados.


## v0.27 — segurança Android e estado de sincronização

- Sessão Android protegida com AES/GCM e chave guardada no Android Keystore.
- Migração única das credenciais antigas em `SharedPreferences` para armazenamento cifrado.
- URL da API configurável no ecrã de autenticação e por `RUNWISE_API_BASE_URL` no Gradle; release sem URL HTTP hard-coded.
- HTTP para `10.0.2.2:8000` disponível apenas no build debug; release exige HTTPS.
- Resposta HTTP 401 limpa a sessão e evita loops de retry do Worker.
- Central de sincronização mostra pendências, conflitos e última sincronização concluída.
- Backend versionado como 0.27.0 e teste de regressão para resolução explícita da versão local.
- A toolchain Android (SDK/Gradle) continua necessária para gerar APK/AAB; foi feita validação estática nesta entrega.


### v0.27 — execução de treino
Cada sessão planeada pode ser aberta numa ficha de execução com instruções por tipo de treino, objetivos e ações de conclusão/salto.


## v0.27 — execução real
A ficha de treino permite guardar distância, duração, ritmo, FC média, esforço percebido e notas, preservando o treino planeado e marcando a sessão como concluída.


## Release 1.0.0

A API usa PBKDF2-HMAC-SHA256 para palavras-passe. Em produção, mantenha `JWT_SECRET` forte, PostgreSQL, HTTPS e `APP_ENV=production`.

### Validação local
```bash
cd backend
PYTHONPATH=. pytest -q
```

### Android
Abra `android/` no Android Studio com Android SDK configurado e execute os testes/instrumentação num emulador ou dispositivo real. Este pacote não inclui um SDK Android nem um Gradle Wrapper gerado localmente.

## Build cloud com Codemagic

O projeto inclui `codemagic.yaml` na raiz do repositório. Ele define:

- `runwise-android-debug`: gera um APK instalável de teste em `android/app/build/outputs/apk/debug/`.
- `runwise-android-release`: gera um APK release assinado, depois de configurar no Codemagic um Android keystore com a referência `runwise_release`.

No Codemagic, o repositório deve ser ligado e o workflow pode ser iniciado manualmente. O projeto Android fica na subpasta `android/`, por isso os workflows usam essa diretoria como working directory.

Para o release assinado, em Codemagic → Team settings → Code signing identities → Android keystores, carregar o keystore e usar a referência `runwise_release`. O Gradle lê automaticamente `CM_KEYSTORE_PATH`, `CM_KEYSTORE_PASSWORD`, `CM_KEY_ALIAS` e `CM_KEY_PASSWORD` quando o build corre no CI.
