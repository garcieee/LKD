// Keeps an eye on the tickets this phone filed, so the person hears when the city changes one. There is no push: the
// phone asks. It asks the server (through MyTickets, whose change detection decides what is news) every 30 s while
// the app is open, at once when it comes back to the screen, and slower while it is away if the phone lets us show
// notifications. News on screen goes to [onNews] (a banner); news while the app is away becomes a notification.
//
// Quiet by design: no tickets, nothing to ask; a failed ask is retried at twice the wait (up to 5 minutes), without a
// word; away without notification permission, no asking at all. Once the phone has frozen or closed the app, nothing
// runs: nothing reaches a person then.
import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' show AppLifecycleState;

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../features/tickets/ticket_notifier.dart';
import '../features/tickets/ticket_text.dart';
import 'my_tickets.dart';

/// How long to wait between asks while the app is open, and while it is away (a notification is all that is for).
const ticketPoll = Duration(seconds: 30);
const ticketPollAway = Duration(minutes: 2);

/// The longest wait after failures: an offline phone tries again every five minutes.
const ticketPollMax = Duration(minutes: 5);

const _askedKey = 'ticket_alerts_asked_v1';

class TicketWatch {
  TicketWatch(this.mine, {this.notifier, required this.onNews});

  final MyTickets mine;
  final TicketNotifier? notifier; // null: no notifications, news only reaches the screen
  final void Function(List<TicketUpdate> updates) onNews; // the app is on screen: say it there

  StreamSubscription<List<TicketUpdate>>? _sub;
  Timer? _timer;
  bool _started = false;
  bool _stopped = false;
  bool _asking = false; // a refresh is on its way: the next wait starts when it ends
  bool _away = false; // the app is not on screen
  bool _canNotify = false; // away, and the phone lets us show notifications: only then is asking worth it
  int _failures = 0; // refreshes in a row that failed

  /// Reads what the phone kept, asks the server once (the baseline, then the menu's dot), and carries on every
  /// [ticketPoll] while there is a ticket to ask about. Safe to call twice.
  Future<void> start() async {
    if (_started) return;
    _started = true;
    _sub = mine.updates.listen(_news);
    await mine.load();
    mine.addListener(_plan); // the first ticket is sent: the clock starts
    await _ask();
  }

  /// The app went to the background or came back. Away it stops asking unless notifications are allowed, in which
  /// case it asks every [ticketPollAway]; back, it clears its notifications and asks at once.
  Future<void> lifecycle(AppLifecycleState state) async {
    final away = state == AppLifecycleState.paused || state == AppLifecycleState.hidden || state == AppLifecycleState.detached;
    if (!_started || _stopped || away == _away) return;
    _away = away;
    _timer?.cancel();
    _timer = null;
    if (away) {
      _canNotify = await _allowed();
      if (_away) _plan();
    } else {
      _canNotify = false;
      _failures = 0;
      unawaited(_clear());
      await _ask();
    }
  }

  /// Asks the phone for permission to show notifications, once ever: the moment is the first ticket the person sends,
  /// when there is something to hear about. Android asks the person once or twice at most, so asking again is no use.
  Future<void> askOnce() async {
    final n = notifier;
    if (n == null) return;
    try {
      final prefs = await SharedPreferences.getInstance();
      if (prefs.getBool(_askedKey) ?? false) return;
      await prefs.setBool(_askedKey, true);
      await n.ask();
    } catch (e) {
      debugPrint('ticket alerts: could not ask for permission: $e');
    }
  }

  void dispose() {
    _stopped = true;
    _timer?.cancel();
    _sub?.cancel();
    mine.removeListener(_plan);
  }

  // Waits, then asks. Only one wait or ask is ever pending.
  void _plan() {
    if (!_started || _stopped) return;
    if (mine.tickets.isEmpty || (_away && !_canNotify)) {
      _timer?.cancel();
      _timer = null;
      return;
    }
    if (_timer != null || _asking) return; // already waiting, or _ask plans the next one
    final wait = (_away ? ticketPollAway : ticketPoll) * math.pow(2, math.min(_failures, 8)).toInt();
    _timer = Timer(wait < ticketPollMax ? wait : ticketPollMax, _ask);
  }

  Future<void> _ask() async {
    _timer?.cancel();
    _timer = null;
    if (_asking || _stopped) return;
    _asking = true;
    try {
      await mine.refresh(); // never throws: a failure is `mine.error`
    } finally {
      _asking = false;
    }
    _failures = mine.error == null ? 0 : _failures + 1;
    _plan();
  }

  // The city changed tickets: tell the screen, or the notification tray when the app is away.
  void _news(List<TicketUpdate> updates) {
    if (!_away) {
      onNews(updates);
      return;
    }
    final n = notifier;
    if (n == null || !_canNotify) return; // the person finds the dot on their return
    unawaited(_notify(n, TicketAlert(updates)));
  }

  Future<void> _notify(TicketNotifier n, TicketAlert alert) async {
    try {
      await n.show(title: alert.title, body: alert.body, payload: alert.only?.id ?? '');
    } catch (e) {
      debugPrint('ticket alerts: could not show a notification: $e'); // the dot is still there
    }
  }

  Future<bool> _allowed() async {
    try {
      return await notifier?.allowed() ?? false;
    } catch (_) {
      return false;
    }
  }

  Future<void> _clear() async {
    try {
      await notifier?.clear();
    } catch (_) {} // a notification left in the tray is a small thing
  }
}
