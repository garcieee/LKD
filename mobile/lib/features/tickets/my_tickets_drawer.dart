// The menu: the tickets this phone filed and where each one stands. Opens from the burger button at the top left of
// the map. A ticket shows its ID (the code the dashboard shows), its status in plain words, and the notes the city
// left: why it was not accepted, or what it said on confirming or fixing it. Pull down to ask the server again.
import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../map/pin_chip.dart';
import '../../state/my_tickets.dart';
import '../../theme.dart';
import 'ticket_text.dart';

class MyTicketsDrawer extends StatelessWidget {
  const MyTicketsDrawer({super.key, required this.mine, required this.onOpen});

  final MyTickets mine;
  final void Function(Report ticket) onOpen;

  @override
  Widget build(BuildContext context) {
    return Drawer(
      backgroundColor: paper,
      child: SafeArea(
        child: ListenableBuilder(
          listenable: mine,
          builder: (context, _) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 18, 20, 4),
                child: Semantics(
                  header: true,
                  child: const Text(
                    'My tickets',
                    style: TextStyle(fontFamily: serif, fontSize: 26, fontWeight: FontWeight.w500),
                  ),
                ),
              ),
              const Padding(
                padding: EdgeInsets.fromLTRB(20, 0, 20, 10),
                child: Text('Reports you sent from this phone', style: TextStyle(fontSize: 12, color: muted)),
              ),
              if (mine.refreshing) const LinearProgressIndicator(minHeight: 2, color: navy),
              if (mine.error != null)
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 4, 20, 4),
                  child: Text(
                    "Couldn't update: ${mine.error} Showing what we knew.",
                    style: const TextStyle(fontSize: 12, color: warn),
                  ),
                ),
              const Divider(height: 1, color: hairline),
              Expanded(
                child: RefreshIndicator(
                  onRefresh: mine.refresh,
                  child: mine.tickets.isEmpty
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          padding: const EdgeInsets.fromLTRB(20, 28, 20, 20),
                          children: const [
                            Icon(Icons.inbox_outlined, size: 36, color: muted),
                            SizedBox(height: 10),
                            Text('No tickets yet', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                            SizedBox(height: 4),
                            Text(
                              'Photos and SOS you send show up here, with where each one stands and what the city said.',
                              style: TextStyle(fontSize: 13, color: muted),
                            ),
                          ],
                        )
                      : ListView.separated(
                          physics: const AlwaysScrollableScrollPhysics(),
                          itemCount: mine.tickets.length,
                          separatorBuilder: (_, _) => const Divider(height: 1, color: hairline),
                          itemBuilder: (context, i) {
                            final t = mine.tickets[i];
                            return TicketTile(ticket: t, isNews: mine.isNews(t), onTap: () => onOpen(t));
                          },
                        ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class TicketTile extends StatelessWidget {
  const TicketTile({super.key, required this.ticket, required this.isNews, required this.onTap});

  final Report ticket;
  final bool isNews; // its status changed since the person last looked
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = ticket;
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 14, 16, 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    t.label,
                    style: const TextStyle(fontFamily: serif, fontSize: 18, fontWeight: FontWeight.w500),
                  ),
                ),
                const SizedBox(width: 8),
                Text(ago(t.createdAt), style: const TextStyle(fontSize: 12, color: muted)),
              ],
            ),
            const SizedBox(height: 6),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                StatusChip(t.status),
                if (isNews)
                  const DecoratedBox(
                    decoration: BoxDecoration(color: sosRed, borderRadius: BorderRadius.all(Radius.circular(4))),
                    child: Padding(
                      padding: EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                      child: Text(
                        'NEW',
                        style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: Colors.white, letterSpacing: 0.4),
                      ),
                    ),
                  ),
                Text(
                  t.code,
                  style: const TextStyle(
                    fontSize: 11,
                    color: muted,
                    letterSpacing: 0.3,
                    fontFeatures: [FontFeature.tabularFigures()],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(ticketMessage(t), style: const TextStyle(fontSize: 13)),
            for (final n in ticketNotes(t)) ...[
              const SizedBox(height: 8),
              DecoratedBox(
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: const BorderRadius.all(Radius.circular(6)),
                  border: Border(left: BorderSide(color: n.bad ? warn : navy, width: 3)),
                ),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        n.label.toUpperCase(),
                        style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: muted, letterSpacing: 0.4),
                      ),
                      const SizedBox(height: 2),
                      Text(n.text, style: const TextStyle(fontSize: 13)),
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
