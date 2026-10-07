// The tickets this phone filed: kept in the phone's storage, refreshed from the server, flagged when one has news.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/state/my_tickets.dart';
import 'package:shared_preferences/shared_preferences.dart';

// A ticket as /my-tickets sends it. `created` and `updated` are minutes after 07:00 UTC.
Map<String, dynamic> json(
  String id, {
  String status = 'open',
  int created = 0,
  int? updated,
  String category = 'pothole',
  Map<String, dynamic> more = const {},
}) {
  String at(int min) => DateTime.utc(2026, 10, 7, 7, min).toIso8601String();
  return {
    'id': id,
    'category': category,
    'lat': 14.5547,
    'lng': 121.0244,
    'heading': null,
    'note': '',
    'photo_url': '/photos/$id.jpg',
    'status': status,
    'created_at': at(created),
    'updated_at': at(updated ?? created),
    ...more,
  };
}

Report ticket(String id, {String status = 'open', int created = 0, int? updated, Map<String, dynamic> more = const {}}) =>
    Report.fromJson(json(id, status: status, created: created, updated: updated, more: more));

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  // Starts a fresh store, as the app does on its next launch.
  MyTickets launch([FetchMine? fetch]) => MyTickets(fetch ?? (_) async => const []);

  test('a new phone has no tickets and no news', () async {
    final mine = launch();
    await mine.load();
    expect(mine.tickets, isEmpty);
    expect(mine.news, 0);
  });

  test('a ticket the phone sends is kept for the next launch, with its notes', () async {
    final first = launch();
    await first.add(ticket('a', more: {'verified_note': 'A crew has been told.', 'handler': 'Ana Reyes'}));

    final second = launch();
    await second.load();
    expect(second.tickets.map((t) => t.id), ['a']);
    expect(second.tickets.single.verifiedNote, 'A crew has been told.');
    expect(second.tickets.single.handler, 'Ana Reyes');
  });

  test('tickets are listed newest first, and sending the same one twice keeps one', () async {
    final mine = launch();
    await mine.add(ticket('old', created: 1));
    await mine.add(ticket('new', created: 30));
    await mine.add(ticket('old', created: 1, status: 'verified'));
    expect(mine.tickets.map((t) => t.id), ['new', 'old']);
    expect(mine.tickets.last.status, 'verified');
  });

  test('only the newest hundred are kept, which is what the server takes at a time', () async {
    final mine = launch();
    for (var n = 0; n < maxTickets + 5; n++) {
      await mine.add(ticket('t$n', created: n % 50, more: {'created_at': DateTime.utc(2026, 10, 7, 7).add(Duration(minutes: n)).toIso8601String()}));
    }
    expect(mine.tickets, hasLength(maxTickets));
    expect(mine.tickets.first.id, 't${maxTickets + 4}');
    expect(mine.tickets.any((t) => t.id == 't0'), isFalse, reason: 'the oldest were let go');
  });

  test('refresh asks the server for every id and shows what came back', () async {
    List<String>? asked;
    final mine = launch((ids) async {
      asked = ids;
      return [ticket('a', status: 'verified', updated: 20, more: {'verified_note': 'Seen.'})];
    });
    await mine.add(ticket('a'));
    await mine.refresh();
    expect(asked, ['a']);
    expect(mine.tickets.single.status, 'verified');
    expect(mine.tickets.single.verifiedNote, 'Seen.');
    expect(mine.error, isNull);
    expect(mine.refreshing, isFalse);
  });

  test('a refresh is kept for the next launch', () async {
    final mine = launch((_) async => [ticket('a', status: 'fixed', updated: 20, more: {'resolved_note': 'Filled.'})]);
    await mine.add(ticket('a'));
    await mine.refresh();
    final next = launch();
    await next.load();
    expect(next.tickets.single.status, 'fixed');
    expect(next.tickets.single.resolvedNote, 'Filled.');
  });

  test('a ticket the server no longer knows stays as the phone last saw it', () async {
    final mine = launch((_) async => [ticket('b', status: 'assigned', created: 5, updated: 9)]);
    await mine.add(ticket('a', status: 'verified', created: 1));
    await mine.add(ticket('b', created: 5));
    await mine.refresh();
    final byId = {for (final t in mine.tickets) t.id: t};
    expect(byId['a']!.status, 'verified', reason: 'pruned on the server: unchanged here');
    expect(byId['b']!.status, 'assigned');
  });

  test('when the server cannot be reached the list stays and says why', () async {
    final mine = launch((_) async => throw const ApiException("Can't reach the server."));
    await mine.add(ticket('a', status: 'verified'));
    await mine.refresh();
    expect(mine.tickets.single.status, 'verified');
    expect(mine.error, "Can't reach the server.");
    expect(mine.refreshing, isFalse, reason: 'the spinner must not stay on');
  });

  test('an answer the app cannot read is an error line, not a stuck spinner', () async {
    final mine = launch((_) async => throw const FormatException('odd'));
    await mine.add(ticket('a'));
    await mine.refresh();
    expect(mine.error, isNotNull);
    expect(mine.refreshing, isFalse);
    expect(mine.tickets, hasLength(1));
  });

  test('with no tickets there is nothing to ask the server', () async {
    var calls = 0;
    final mine = launch((_) async {
      calls++;
      return const [];
    });
    await mine.refresh();
    expect(calls, 0);
  });

  test('a status change is news until the person has looked, and a ticket just sent is not news', () async {
    final mine = launch((_) async => [ticket('a', status: 'verified', updated: 20)]);
    await mine.add(ticket('a'));
    expect(mine.news, 0, reason: 'they just sent it');
    await mine.refresh();
    expect(mine.news, 1);
    expect(mine.isNews(mine.tickets.single), isTrue);
    await mine.markSeen();
    expect(mine.news, 0);
    expect(mine.isNews(mine.tickets.single), isFalse);
  });

  test('news survives a restart, and looking at it survives too', () async {
    final first = launch((_) async => [ticket('a', status: 'rejected', updated: 20, more: {'rejected_note': 'Duplicate.'})]);
    await first.add(ticket('a'));
    await first.refresh();

    final second = launch();
    await second.load();
    expect(second.news, 1, reason: 'the dot is still there after the app was closed');
    await second.markSeen();

    final third = launch();
    await third.load();
    expect(third.news, 0);
  });

  test('a note added after the last look is news too, though the status is the same', () async {
    final mine = launch((_) async => [ticket('a', status: 'verified', updated: 40, more: {'verified_note': 'A crew is coming.'})]);
    await mine.add(ticket('a', status: 'verified', updated: 20));
    await mine.refresh();
    expect(mine.news, 1);
  });

  test('damaged storage starts an empty list instead of failing, and one bad ticket does not lose the rest', () async {
    SharedPreferences.setMockInitialValues({'my_tickets_v1': '{not json'});
    final broken = launch();
    await broken.load();
    expect(broken.tickets, isEmpty);

    SharedPreferences.setMockInitialValues({
      'my_tickets_v1': jsonEncode({
        'tickets': [json('good'), {'id': 'bad'}, 'junk'],
        'seen': <String, dynamic>{},
      }),
    });
    final partly = launch();
    await partly.load();
    expect(partly.tickets.map((t) => t.id), ['good']);
  });

  test('a ticket can be added before load() finishes without erasing what was kept', () async {
    final first = launch();
    await first.add(ticket('kept'));
    final second = launch();
    await second.add(ticket('new', created: 10)); // no load() first, as map_view's report flow might
    expect(second.tickets.map((t) => t.id).toSet(), {'kept', 'new'});
  });
}
