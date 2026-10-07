// The ticket fields the app reads (the city's notes, the handler, the ID) and the /my-tickets call.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lakad/api/api_client.dart';

Map<String, dynamic> serverTicket({Map<String, dynamic> more = const {}}) => {
  'id': '3f2a9c01deadbeef',
  'category': 'pothole',
  'severity': 2,
  'lat': 14.5547,
  'lng': 121.0244,
  'heading': null,
  'note': 'deep, by the jeepney stop',
  'photo_url': '/photos/3f2a9c01deadbeef.jpg',
  'status': 'fixed',
  'created_at': '2026-10-07T07:31:05+00:00',
  'updated_at': '2026-10-07T09:02:00+00:00',
  'handler': 'Ana Reyes · Public Works',
  'verified_note': 'A crew has been told.',
  'rejected_note': null,
  'resolved_note': 'Filled and sealed.',
  ...more,
};

ApiClient apiWith(MockClient mock) =>
    ApiClient(client: mock, base: 'http://server', timeout: const Duration(milliseconds: 50));

http.Response jsonResponse(Object body, int status) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});

void main() {
  group('Report', () {
    test('reads the handler, the three notes, when it last changed and its ticket', () {
      final r = Report.fromJson(serverTicket(more: {'ticket_id': 'b7e1ffaa00'}));
      expect(r.handler, 'Ana Reyes · Public Works');
      expect((r.verifiedNote, r.rejectedNote, r.resolvedNote), ('A crew has been told.', null, 'Filled and sealed.'));
      expect(r.updatedAt, DateTime.utc(2026, 10, 7, 9, 2));
      expect(r.ticketId, 'b7e1ffaa00');
    });

    test('a report from the public list has none of them, and still reads', () {
      final r = Report.fromJson({...serverTicket(), 'handler': null, 'verified_note': null, 'resolved_note': null}
        ..remove('updated_at'));
      expect((r.handler, r.verifiedNote, r.resolvedNote, r.ticketId), (null, null, null, null));
      expect(r.updatedAt, r.createdAt, reason: 'no updated_at: the day it was filed');
    });

    test("shows the ticket's ID the way the dashboard does: LKD- and six capitals", () {
      expect(Report.fromJson(serverTicket()).code, 'LKD-3F2A9C', reason: 'no ticket yet: its own id');
      expect(Report.fromJson(serverTicket(more: {'ticket_id': 'b7e1ffaa00'})).code, 'LKD-B7E1FF', reason: 'its ticket');
      expect(Report.fromJson(serverTicket(more: {'id': 'ab'})).code, 'LKD-AB', reason: 'a short id does not crash');
    });

    test('keeps the JSON it came from, so a phone can store the ticket and read it back the same', () {
      final json = serverTicket();
      final back = Report.fromJson(jsonDecode(jsonEncode(Report.fromJson(json).source)) as Map<String, dynamic>);
      expect((back.id, back.status, back.verifiedNote, back.updatedAt), ('3f2a9c01deadbeef', 'fixed', 'A crew has been told.', DateTime.utc(2026, 10, 7, 9, 2)));
    });

    test('a rejected ticket reads as rejected, not as open', () {
      expect(Report.fromJson(serverTicket(more: {'status': 'rejected'})).status, 'rejected');
      expect(statusLabels['rejected'], 'Rejected');
    });
  });

  group('ApiClient.myTickets', () {
    test('asks /my-tickets for the ids, in order, and reads the answer with its notes', () async {
      late Uri asked;
      final api = apiWith(
        MockClient((req) async {
          asked = req.url;
          return jsonResponse([serverTicket(), serverTicket(more: {'id': 'b7e1ffaa00', 'status': 'rejected', 'rejected_note': 'Duplicate.'})], 200);
        }),
      );
      final got = await api.myTickets(['3f2a9c01deadbeef', 'b7e1ffaa00']);
      expect(asked.path, '/my-tickets');
      expect(asked.queryParameters['ids'], '3f2a9c01deadbeef,b7e1ffaa00');
      expect(got.map((t) => t.status), ['fixed', 'rejected']);
      expect(got.last.rejectedNote, 'Duplicate.');
    });

    test('with no ids it does not call the server at all', () async {
      var calls = 0;
      final api = apiWith(
        MockClient((_) async {
          calls++;
          return jsonResponse(const [], 200);
        }),
      );
      expect(await api.myTickets(const []), isEmpty);
      expect(calls, 0);
    });

    test('a failed call is an ApiException with a message fit to show', () {
      final api = apiWith(MockClient((_) async => jsonResponse({'detail': 'Try later.'}, 503)));
      expect(api.myTickets(['a']), throwsA(isA<ApiException>().having((e) => e.message, 'message', 'Try later.')));
    });
  });
}
