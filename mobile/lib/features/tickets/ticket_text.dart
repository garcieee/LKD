// What a ticket says to the person who filed it: where it stands in plain words, and the notes the city left.
// Shared by the menu's list and the ticket card, which is why it lives apart from both. Also what a notice says when
// the city changes a ticket.
import '../../api/api_client.dart';
import '../../state/my_tickets.dart';

/// What a status means to the person who filed the ticket.
String ticketMessage(Report r) => switch (r.status) {
  'verified' => 'Confirmed by the city.',
  'assigned' => r.handler == null ? 'Assigned to a handler.' : 'Assigned to ${r.handler}.',
  'fixed' => r.handler == null ? 'Resolved.' : 'Resolved. Handled by ${r.handler}.',
  'rejected' => 'Not accepted.',
  _ => 'Received. Waiting for the city to review it.',
};

typedef TicketNote = ({String label, String text, bool bad});

/// The notes to show on a ticket: the reason when it was rejected (only while it is), the note left on confirming
/// (kept once confirmed), and the note left on fixing it. Empty notes are skipped.
List<TicketNote> ticketNotes(Report r) {
  bool has(String? s) => s != null && s.trim().isNotEmpty;
  return [
    if (r.status == 'rejected' && has(r.rejectedNote)) (label: 'Why it was not accepted', text: r.rejectedNote!, bad: true),
    if (const {'verified', 'assigned', 'fixed'}.contains(r.status) && has(r.verifiedNote))
      (label: 'Note from the city', text: r.verifiedNote!, bad: false),
    if (r.status == 'fixed' && has(r.resolvedNote)) (label: 'Note on the fix', text: r.resolvedNote!, bad: false),
  ];
}

/// What changed on a ticket, in plain words, for a notice: "Confirmed by the city", "Assigned to Ana Reyes", "Back
/// under review". Only the note's existence is mentioned, never its text: a notice can show on a lock screen.
String ticketUpdateLine(TicketUpdate u) {
  final (:now, :before) = u;
  final noted = ticketNotes(now).map((n) => n.text).join('\n');
  final newNote = noted.isNotEmpty && (before == null || ticketNotes(before).map((n) => n.text).join('\n') != noted);
  if (before != null && before.status == now.status) {
    // The same status: the handler changed, or a note was added. (Neither: the server touched it, so say where it is.)
    if (now.handler != null && now.handler != before.handler && now.status == 'assigned') return 'Assigned to ${now.handler}';
    if (newNote) return 'New note from the city';
  }
  final status = switch (now.status) {
    'verified' => 'Confirmed by the city',
    'assigned' => now.handler == null ? 'Assigned to a handler' : 'Assigned to ${now.handler}',
    'fixed' => 'Resolved',
    'rejected' => 'Not accepted',
    _ => 'Back under review', // open again: a ticket the person just sent never reaches here, only a reopened one
  };
  return newNote ? '$status · note from the city' : status;
}

/// The notice for tickets the city changed: one ticket by its ID and what happened to it, several as a count.
class TicketAlert {
  TicketAlert(List<TicketUpdate> updates)
    : assert(updates.isNotEmpty),
      only = updates.length == 1 ? updates.single.now : null,
      title = updates.length == 1 ? updates.single.now.code : 'My tickets',
      body = updates.length == 1 ? ticketUpdateLine(updates.single) : '${updates.length} of your tickets were updated';

  final Report? only; // the ticket a tap opens; null opens the list
  final String title; // "LKD-3F2A9C"
  final String body; // "Confirmed by the city"

  /// On one line, for a banner: "LKD-3F2A9C: Confirmed by the city".
  String get text => only == null ? body : '$title: $body';
}
