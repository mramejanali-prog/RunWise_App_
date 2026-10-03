# RunWise 1.0.0 — validação de release

## Backend

```bash
cd backend
python -m venv .venv
# ativar .venv
pip install -r requirements.txt
PYTHONPATH=. pytest -q
```

A suíte atual contém 9 testes de regressão/integridade.

## Android

Abrir `android/` no Android Studio com:

- Android SDK 35
- JDK 17 ou compatível com a versão do Android Gradle Plugin
- dependências Gradle resolvidas por `google()` e `mavenCentral()`

Configurar `android/keystore.properties` para release assinada e executar:

```bash
./gradlew :app:assembleRelease
./gradlew :app:bundleRelease
```

Depois testar em dispositivo/emulador Android real:

1. registo/login;
2. Health Connect e permissões;
3. importação de corrida;
4. execução planeada;
5. sincronização cloud/offline;
6. Calendar;
7. notificações;
8. relatórios;
9. conflitos de sincronização;
10. logout e nova sessão.

## Integrações externas

TCHACO só deve ser ligado através de API/webhook oficialmente autorizado. Google Calendar usa o calendário Android configurado no dispositivo; OAuth Google dedicado requer credenciais do projeto.
