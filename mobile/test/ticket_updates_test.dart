// When does a refresh tell the person about a ticket? MyTickets.updates is the one place that decides: only a change the
// city made since the phone last heard, once, with several changes together. And what each notice says.
import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/features/tickets/ticket_text.dart';
import 'package:lakad/state/my_tickets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'ticket_fixtures.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  // What the server answers right now, and what a phone that is listening heard.
  late List<Report> served;
  Object? failing;
  final heard = <List<TicketUpdate>>[];

  MyTickets launch() => MyTickets((_) async {
    if (failing != null) throw failing!;
    return served;
  })..updates.listen(heard.add);

  Future<void> refresh(MyTickets mine) async {
    await mine.refresh();
    await pumpEventQueue(); // the stream delivers a moment later
  }

  setUp(() {
    served = const [];
    failing = null;
    heard.clear();
  });

  test('a change to a ticket sent from this phone is announced once, with what it was before', () async {
    final mine = launch();
    await mine.add(ticket('a'));
    served = [ticket('a', status: 'verified', updated: 20)];
    await refresh(mine);
    expect(heard, hasLength(1));
    expect(heard.single.single.now.status, 'verified');
    expect(heard.single.single.before?.status, 'open');
    await refresh(mine);
    await refresh(mine);
    expect(heard, hasLength(1), reason: 'the same change is not announced again');
    expect(mine.news, 1, reason: 'it is still news for the dot, until they look');
  });

  test('what the phone kept from the last run is only a baseline: the first fetch of it is not announced', () async {
    final before = launch();
    await before.add(ticket('a'));

    final mine = launch(); // the app opened again; the city changed the ticket while it was closed
    served = [ticket('a', status: 'verified', updated: 20)];
    await refresh(mine);
    expect(heard, isEmpty);
    expect(mine.news, 1, reason: 'the red dot and the NEW tag are how they hear that one');

    served = [ticket('a', status: 'assigned', updated: 30, more: {'handler': 'Ana Reyes'})];
    await refresh(mine);
    expect(heard.single.single.now.status, 'assigned', reason: 'a change after the baseline is announced');
  });

  test('a ticket with nothing new is not announced, and nor is one the server forgot', () async {
    final mine = launch();
    await mine.add(ticket('a'));
    await mine.add(ticket('b', created: 5));
    served = [ticket('a')]; // b was pruned on the server
    await refresh(mine);
    expect(heard, isEmpty);
  });

  test('several changes found together arrive as one list', () async {
    final mine = launch();
    await mine.add(ticket('a'));
    await mine.add(ticket('b', created: 5));
    await mine.add(ticket('c', created: 9));
    served = [
      ticket('a', status: 'verified', updated: 20),
      ticket('b', created: 5, status: 'rejected', updated: 21, more: {'rejected_note': 'A duplicate.'}),
      ticket('c', created: 9), // no news
    ];
    await refresh(mine);
    expect(heard, hasLength(1));
    expect(heard.single.map((u) => u.now.id), ['b', 'a'], reason: 'newest ticket first, like the list');
  });

  test('two changes between asks are one announcement, with the latest state', () async {
    final mine = launch();
    await mine.add(ticket('a'));
    served = [ticket('a', status: 'assigned', updated: 30, more: {'handler': 'Ana Reyes'})]; // confirmed, then assigned
    await refresh(mine);
    expect(heard, hasLength(1));
    expect(ticketUpdateLine(heard.single.single), 'Assigned to Ana Reyes');
  });

  test('a ticket rejected, reopened and confirmed is announced at each step', () async {
    final mine = launch();
    await mine.add(ticket('a'));
    final lines = <String>[];
    Future<void> city(Report r) async {
      served = [r];
      await refresh(mine);
      lines.add(ticketUpdateLine(heard.last.single));
    }

    await city(ticket('a', status: 'rejected', updated: 20, more: {'rejected_note': 'Not a hazard.'}));
    await city(ticket('a', status: 'open', updated: 30, more: {'rejected_note': 'Not a hazard.'})); // the old reason stays on the record
    await city(ticket('a', status: 'verified', updated: 40));
    expect(heard, hasLength(3));
    expect(lines, ['Not accepted · note from the city', 'Back under review', 'Confirmed by the city']);
  });

  test('a failed ask announces nothing, and the change is announced once when an ask works', () async {
    final mine = launch();
    await mine.add(ticket('a'));
    served = [ticket('a', status: 'verified', updated: 20)];
    failing = const ApiException("Can't reach the server.");
    await refresh(mine);
    expect(heard, isEmpty);
    expect(mine.error, isNotNull);
    failing = null;
    await refresh(mine);
    await refresh(mine);
    expect(heard, hasLength(1));
  });

  test('an older answer than the phone has is not a change', () async {
    final mine = launch();
    await mine.add(ticket('a', status: 'verified', updated: 20));
    served = [ticket('a', updated: 10)];
    await refresh(mine);
    expect(heard, isEmpty);
  });

  test('opening a ticket from its notice clears that one from the dot, and the others stay', () async {
    final mine = launch();
    await mine.add(ticket('a'));
    await mine.add(ticket('b', created: 5));
    served = [ticket('a', status: 'verified', updated: 20), ticket('b', created: 5, status: 'fixed', updated: 21)];
    await refresh(mine);
    expect(mine.news, 2);
    await mine.markRead('a');
    expect(mine.news, 1);
    expect(mine.isNews(mine.tickets.firstWhere((t) => t.id == 'b')), isTrue);
    await mine.markRead('nope'); // a ticket that is gone is not an error
    expect(mine.news, 1);
  });

  group('what a notice says', () {
    TicketUpdate u(Report now, [Report? before]) => (now: now, before: before);

    test('a new status, in plain words, with the ticket ID', () {
      expect(ticketUpdateLine(u(ticket('a', status: 'verified', updated: 5), ticket('a'))), 'Confirmed by the city');
      expect(ticketUpdateLine(u(ticket('a', status: 'fixed', updated: 5, more: {'handler': 'Ana Reyes'}), ticket('a'))), 'Resolved');
      expect(ticketUpdateLine(u(ticket('a', status: 'rejected', updated: 5), ticket('a'))), 'Not accepted');
      expect(ticketUpdateLine(u(ticket('a', status: 'assigned', updated: 5), ticket('a'))), 'Assigned to a handler');
      final one = TicketAlert([u(ticket('3f2a9c01aa', status: 'verified', updated: 5), ticket('3f2a9c01aa'))]);
      expect((one.title, one.body, one.text), ('LKD-3F2A9C', 'Confirmed by the city', 'LKD-3F2A9C: Confirmed by the city'));
      expect(one.only?.id, '3f2a9c01aa');
    });

    test('a new handler or a new note on a ticket whose status did not change says which', () {
      final was = ticket('a', status: 'assigned', updated: 5, more: {'handler': 'Ana Reyes', 'verified_note': 'A crew is told.'});
      expect(ticketUpdateLine(u(ticket('a', status: 'assigned', updated: 9, more: {'handler': 'Ben Cruz', 'verified_note': 'A crew is told.'}), was)), 'Assigned to Ben Cruz');
      expect(ticketUpdateLine(u(ticket('a', status: 'assigned', updated: 9, more: {'handler': 'Ana Reyes', 'verified_note': 'Crew is on the way.'}), was)), 'New note from the city');
    });

    test('a note that comes with the status is mentioned, but its words are not (a notice can sit on a lock screen)', () {
      final line = ticketUpdateLine(u(ticket('a', status: 'rejected', updated: 5, more: {'rejected_note': 'Blurry photo of my neighbour.'}), ticket('a')));
      expect(line, 'Not accepted · note from the city');
      expect(line, isNot(contains('Blurry')));
    });

    test('several tickets are a count, and a tap opens the list', () {
      final two = TicketAlert([
        u(ticket('a', status: 'verified', updated: 5), ticket('a')),
        u(ticket('b', status: 'fixed', updated: 6), ticket('b')),
      ]);
      expect((two.title, two.body, two.text), ('My tickets', '2 of your tickets were updated', '2 of your tickets were updated'));
      expect(two.only, isNull);
    });

    test('updates to one ticket merge into its latest state, from what the phone knew first', () {
      final merged = mergeUpdates([
        u(ticket('a', status: 'verified', updated: 5), ticket('a')),
        u(ticket('b', status: 'fixed', updated: 6), ticket('b')),
        u(ticket('a', status: 'assigned', updated: 9), ticket('a', status: 'verified', updated: 5)),
      ]);
      expect(merged.map((m) => m.now.id), ['a', 'b']);
      expect((merged.first.now.status, merged.first.before?.status), ('assigned', 'open'));
    });
  });
}
