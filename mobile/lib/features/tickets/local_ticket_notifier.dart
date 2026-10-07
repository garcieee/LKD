// The phone's notification tray, through flutter_local_notifications. Android only: there is no iOS project here.
// Local notifications, so nothing arrives while the app is closed. Every call is safe to make anywhere: a phone or an
// error that cannot show notifications just shows none. Not run on a physical device yet.
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'ticket_notifier.dart';

const _channel = AndroidNotificationDetails(
  'ticket_updates',
  'Ticket updates',
  channelDescription: 'When the city changes a ticket you sent',
  importance: Importance.high,
  priority: Priority.high,
  icon: 'ic_stat_ticket', // android/app/src/main/res/drawable
);

class LocalTicketNotifier implements TicketNotifier {
  final _plugin = FlutterLocalNotificationsPlugin();
  void Function(String payload)? _open;
  Future<bool>? _ready;

  Future<bool> _init() => _ready ??= _start();

  Future<bool> _start() async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) return false;
    try {
      await _plugin.initialize(
        settings: const InitializationSettings(android: AndroidInitializationSettings('ic_stat_ticket')),
        onDidReceiveNotificationResponse: (r) => _open?.call(r.payload ?? ''),
      );
      return true;
    } catch (e) {
      debugPrint('notifications: could not start: $e');
      return false;
    }
  }

  AndroidFlutterLocalNotificationsPlugin? get _android =>
      _plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();

  @override
  Future<bool> allowed() async {
    if (!await _init()) return false;
    try {
      return await _android?.areNotificationsEnabled() ?? false;
    } catch (e) {
      debugPrint('notifications: could not tell if they are allowed: $e');
      return false;
    }
  }

  @override
  Future<bool> ask() async {
    if (!await _init()) return false;
    try {
      return await _android?.requestNotificationsPermission() ?? false;
    } catch (e) {
      debugPrint('notifications: could not ask: $e');
      return false;
    }
  }

  @override
  Future<void> show({required String title, required String body, String? payload}) async {
    if (!await _init()) return;
    try {
      // One notification per ticket: a second change to it replaces the first instead of piling up.
      await _plugin.show(
        id: (payload ?? '').hashCode & 0x7fffffff,
        title: title,
        body: body,
        notificationDetails: const NotificationDetails(android: _channel),
        payload: payload ?? '',
      );
    } catch (e) {
      debugPrint('notifications: could not show one: $e');
    }
  }

  @override
  Future<void> clear() async {
    if (!await _init()) return;
    try {
      await _plugin.cancelAll();
    } catch (e) {
      debugPrint('notifications: could not clear: $e');
    }
  }

  @override
  void whenTapped(void Function(String payload) open) => _open = open;
}
