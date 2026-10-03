# RunWise backend — produção

## Arranque da base de dados

Em produção o backend não executa `create_all()`. A estrutura deve ser criada/atualizada com Alembic:

```bash
cd backend
alembic upgrade head
```

Depois iniciar a API, por exemplo:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

## Variáveis obrigatórias

- `APP_ENV=production`
- `DATABASE_URL=postgresql+psycopg://...`
- `JWT_SECRET` com pelo menos 32 caracteres aleatórios
- `ALLOWED_HOSTS` com os hostnames reais da API
- `CORS_ORIGINS` apenas com origens necessárias

O endpoint `/ready` verifica a conectividade com a base de dados.

## Segurança

Em produção o backend aplica `TrustedHostMiddleware`, desativa Swagger/ReDoc e mantém os cabeçalhos de segurança e limites de pedidos. O rate limit atual é local ao processo; para múltiplos processos/instâncias, deve ser substituído por um mecanismo partilhado (por exemplo Redis) antes de depender dele como controlo distribuído.

## TCHACO

A ingestão por webhook só fica ativa quando `TCHACO_WEBHOOK_SECRET` estiver configurado e a assinatura HMAC-SHA256 for válida. A aplicação não assume endpoints privados da TCHACO.
