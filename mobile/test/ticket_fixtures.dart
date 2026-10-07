// Shared by the ticket-notification tests: a ticket as /my-tickets sends it, and a notification tray that records.
import 'package:lakad/api/api_client.dart';
import 'package:lakad/features/tickets/ticket_notifier.dart';

/// A ticket as the server sends it. [created] and [updated] are minutes after 07:00 UTC on the day of the hackathon.
Report ticket(
  String id, {
  String status = 'open',
  int created = 0,
  int? updated,
  String category = 'pothole',
  Map<String, dynamic> more = const {},
}) {
  String at(int min) => DateTime.utc(2026, 10, 7, 7, min).toIso8601String();
  return Report.fromJson({
    'id': id,
    'category': category,
    'lat': 14.5547,
    'lng': 121.0244,
    'heading': null,
    'note': '',
    'photo_url': category == 'sos' ? '' : '/photos/$id.jpg',
    'status': status,
    'created_at': at(created),
    'updated_at': at(updated ?? created),
    ...more,
  });
}

typedef Shown = ({String title, String body, String payload});

/// The phone's notification tray, standing in for the plugin: what it was asked, and what the person has set.
class FakeNotifier implements TicketNotifier {
  FakeNotifier({this.permitted = true});

  bool permitted; // what the person allowed in Settings
  int asked = 0; // times the permission dialog was requested
  int cleared = 0;
  final shown = <Shown>[];
  void Function(String payload)? tap;

  @override
  Future<bool> allowed() async => permitted;

  @override
  Future<bool> ask() async {
    asked++;
    return permitted;
  }

  @override
  Future<void> show({required String title, required String body, String? payload}) async =>
      shown.add((title: title, body: body, payload: payload ?? ''));

  @override
  Future<void> clear() async => cleared++;

  @override
  void whenTapped(void Function(String payload) open) => tap = open;
}
