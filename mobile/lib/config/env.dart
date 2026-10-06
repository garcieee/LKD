// Values come from env.json: flutter run --dart-define-from-file=env.json
// (copy env.example.json to env.json first).
class Env {
  static const mapboxToken = String.fromEnvironment('MAPBOX_TOKEN');
  static const tomtomKey = String.fromEnvironment('TOMTOM_API_KEY');

  // The one place the server address lives.
  // Real phone: put the laptop's hotspot IP in env.json.
  // 10.0.2.2 is how an Android emulator reaches the host machine.
  static const apiBaseUrl =
      String.fromEnvironment('API_BASE_URL', defaultValue: 'http://10.0.2.2:8000');
}
