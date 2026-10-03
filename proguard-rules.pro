# RunWise release rules.
# Retrofit is not used; JSON parsing is performed with org.json.
# Keep Room generated database metadata available to runtime.
-keep class com.runwise.app.data.** { *; }
