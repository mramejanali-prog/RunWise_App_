# RunWise 1.0.0 — Release candidate

## Implementado nesta versão
- Análise automática da execução contra o treino planeado.
- Comparação de distância, duração e ritmo quando existem alvos equivalentes.
- Classificação explicável: Dentro do objetivo / Próximo do objetivo / Fora do objetivo.
- Score de aderência 0–100, usado apenas como indicador operacional de comparação.
- Indicação de execução mais rápida ou mais lenta que a referência.
- FC média apresentada quando disponível.
- Preserva a separação entre plano prescrito e execução medida.

## Validação
- Backend Python: compileall OK.
- Kotlin MainActivity: contagem estrutural de chaves OK.
- ZIP v0.35 criado em `/mnt/data/runwise_real_v0_35.zip`.
- Build Android completo não executado: este ambiente não possui SDK/Gradle configurado.


## Release 1.0.0 — endurecimento
- Hash de palavras-passe migrado para compatibilidade com bcrypt quando `passlib` está disponível e fallback PBKDF2-HMAC-SHA256 no ambiente de desenvolvimento sem essa dependência.
- Testes backend executáveis sem dependências externas adicionais.
- A versão da API passa a 1.0.0.
- A validação Android continua a exigir Android SDK/Gradle e um dispositivo/emulador real.
