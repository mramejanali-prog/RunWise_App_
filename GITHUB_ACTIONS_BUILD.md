# Build the RunWise APK for free with GitHub Actions

GitHub Actions provides free standard runners for public repositories. This project includes `.github/workflows/android-apk.yml`, which builds a debug APK and uploads it as an artifact.

## Steps

1. Create a GitHub account if you do not already have one.
2. Create a **public** repository, for example `runwise`.
3. Upload the contents of this project to that repository (the `.github` folder must be included).
4. Open **Actions** → **Build RunWise APK**.
5. Run **Build RunWise APK** manually, or push to `main`.
6. When the workflow finishes, open the workflow run and download the **RunWise-debug-apk** artifact.
7. Extract the downloaded artifact and install the APK on the Android phone.

The workflow does not require Codemagic billing.

For a production release, use a private signing keystore later; do not commit the keystore or passwords to GitHub.
