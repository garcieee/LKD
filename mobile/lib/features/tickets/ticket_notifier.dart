// What the app needs from the phone's notification tray, and nothing else: the plugin behind it
// (local_ticket_notifier.dart) is the only file that imports it, so tests bring a fake and the rest of the app never
// sees the plugin. Notifications here are local: shown by the app itself while it is running, never pushed.

abstract interface class TicketNotifier {
  /// Whether the phone lets the app show notifications right now (the person can turn them off in Settings).
  Future<bool> allowed();

  /// Asks for permission with the system's own dialog, which Android shows only once or twice. True once allowed.
  Future<bool> ask();

  /// Posts one. [payload] comes back to [whenTapped]: a ticket's id, or empty for the list.
  Future<void> show({required String title, required String body, String? payload});

  /// Takes down what [show] posted (the person is back in the app).
  Future<void> clear();

  /// What to do when the person taps one of them, while the app is running.
  void whenTapped(void Function(String payload) open);
}
