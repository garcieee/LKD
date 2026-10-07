// The tickets this phone filed. The app has no accounts, so it keeps the reports it sent (and the last status it saw)
// in the phone's own storage, and asks the server for their latest status with /my-tickets. A ticket whose status
// changed since the person last opened the list is "news": the menu button wears a dot until they look. A refresh
// that finds news also says so on [MyTickets.updates], once, for the notices (see ticket_watch.dart).
import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api_client.dart';

typedef FetchMine = Future<List<Report>> Function(List<String> ids);

/// A ticket the city changed since the phone last heard of it: what it is [now], and what the phone knew [before]
/// (null when it did not know).
typedef TicketUpdate = ({Report now, Report? before});

/// Several updates to one ticket become one: its latest state, from what the phone knew first. Order of first mention.
List<TicketUpdate> mergeUpdates(Iterable<TicketUpdate> updates) {
  final byId = <String, TicketUpdate>{};
  for (final u in updates) {
    final first = byId[u.now.id];
    byId[u.now.id] = (now: u.now, before: first == null ? u.before : first.before);
  }
  return byId.values.toList();
}

const _storeKey = 'my_tickets_v1';

/// What /my-tickets takes at a time. The oldest tickets beyond it are forgotten here (they stay on the server).
const maxTickets = 100;

class MyTickets extends ChangeNotifier {
  MyTickets([FetchMine? fetch]) : _fetch = fetch ?? api.myTickets;

  final FetchMine _fetch;

  List<Report> tickets = const []; // newest first
  bool refreshing = false;
  String? error; // why the last refresh failed, fit to show: the list is then what the phone last knew
  final _seen = <String, DateTime>{}; // ticket id -> its updatedAt when the person last looked
  // ticket id -> its updatedAt when this run last told the person about it. A ticket with no entry has not been fetched
  // since the app opened: its first fetch is the baseline, never a notice (the dot and NEW tag cover what changed
  // while the app was closed). Not stored: a new run starts from its own baseline.
  final _told = <String, DateTime>{};
  final _updates = StreamController<List<TicketUpdate>>.broadcast();
  Future<void>? _reading;

  /// What the city changed, one list per refresh that found any: every ticket that is news and has not been told yet,
  /// so a ticket is announced once for each change and several changes arrive together. Nothing for a failed refresh.
  Stream<List<TicketUpdate>> get updates => _updates.stream;

  /// Whether a ticket changed since the person last looked: a new status, or a note from the city.
  bool isNews(Report t) {
    final seen = _seen[t.id];
    return seen == null || t.updatedAt.isAfter(seen);
  }

  int get news => tickets.where(isNews).length;

  /// Reads what the phone kept. Safe to call twice. A phone whose storage fails shows an empty list and carries on.
  Future<void> load() => _reading ??= _read();

  Future<void> _read() async {
    try {
      final stored = (await SharedPreferences.getInstance()).getString(_storeKey);
      if (stored != null) {
        final data = jsonDecode(stored) as Map<String, dynamic>;
        tickets = [
          for (final t in data['tickets'] as List) ?_parse(t),
        ];
        for (final MapEntry(:key, :value) in (data['seen'] as Map<String, dynamic>? ?? {}).entries) {
          if (DateTime.tryParse('$value') case final at?) _seen[key] = at;
        }
      }
    } catch (e) {
      debugPrint('my tickets: could not read the saved list: $e'); // start empty rather than fail
    }
    notifyListeners();
  }

  static Report? _parse(Object? json) {
    try {
      return Report.fromJson(Map<String, dynamic>.from(json as Map));
    } catch (_) {
      return null; // one bad entry does not lose the rest
    }
  }

  /// Keeps a ticket the phone just sent, as already seen: the person knows about it.
  Future<void> add(Report ticket) async {
    await load();
    _seen[ticket.id] = ticket.updatedAt;
    _told[ticket.id] = ticket.updatedAt; // from here on, a change to it is a notice
    _replace([ticket, ...tickets.where((t) => t.id != ticket.id)]);
    await _save();
    notifyListeners();
  }

  /// Asks the server for the latest of every ticket. A failure keeps what the phone knew and says why in [error].
  Future<void> refresh() async {
    await load();
    if (tickets.isEmpty || refreshing) return;
    refreshing = true;
    error = null;
    notifyListeners();
    try {
      final before = {for (final t in tickets) t.id: t};
      final fresh = {for (final t in await _fetch([for (final t in tickets) t.id])) t.id: t};
      // A ticket the server no longer knows (pruned) stays as it was last seen.
      _replace([for (final t in tickets) fresh[t.id] ?? t]);
      await _save();
      _tell(before);
    } on ApiException catch (e) {
      error = e.message;
    } catch (_) {
      error = "Can't read the server's answer."; // an odd reply must not leave the spinner on
    } finally {
      refreshing = false;
      notifyListeners();
    }
  }

  /// What this refresh found: the news the person has not been told about yet. [before] is what the phone knew.
  void _tell(Map<String, Report> before) {
    final news = <TicketUpdate>[];
    for (final t in tickets) {
      final told = _told[t.id];
      _told[t.id] = t.updatedAt;
      if (told != null && t.updatedAt.isAfter(told) && isNews(t)) news.add((now: t, before: before[t.id]));
    }
    if (news.isNotEmpty && !_updates.isClosed) _updates.add(news);
  }

  /// The person opened one ticket (from a notice): it is no longer news, the others still are.
  Future<void> markRead(String id) async {
    await load();
    final t = tickets.where((t) => t.id == id).firstOrNull;
    if (t == null || !isNews(t)) return;
    _seen[id] = t.updatedAt;
    await _save();
    notifyListeners();
  }

  /// The person has looked at the list: nothing is news any more.
  Future<void> markSeen() async {
    await load();
    if (tickets.isEmpty || news == 0) return;
    for (final t in tickets) {
      _seen[t.id] = t.updatedAt;
    }
    await _save();
    notifyListeners();
  }

  void _replace(List<Report> next) {
    tickets = ([...next]..sort((a, b) => b.createdAt.compareTo(a.createdAt))).take(maxTickets).toList();
    _seen.removeWhere((id, _) => !tickets.any((t) => t.id == id));
    _told.removeWhere((id, _) => !tickets.any((t) => t.id == id));
  }

  @override
  void dispose() {
    _updates.close();
    super.dispose();
  }

  Future<void> _save() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(
        _storeKey,
        jsonEncode({
          'tickets': [for (final t in tickets) t.source],
          'seen': {for (final MapEntry(:key, :value) in _seen.entries) key: value.toIso8601String()},
        }),
      );
    } catch (e) {
      debugPrint('my tickets: could not save the list: $e'); // the list still works for this session
    }
  }
}
