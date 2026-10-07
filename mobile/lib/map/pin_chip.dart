// The card that opens on a report pin: photo, category, status chip, age and note.
import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../features/tickets/ticket_text.dart';
import '../layers/reports_layer.dart';
import '../theme.dart';

Future<void> showReportSheet(BuildContext context, Report report, {bool mine = false}) => showModalBottomSheet<void>(
  context: context,
  showDragHandle: true,
  isScrollControlled: true, // a long note may need more than the default 9/16 of the screen
  useSafeArea: true,
  builder: (_) => _ReportCard(report, mine: mine),
);

/// "12 min ago".
String ago(DateTime time, [DateTime? now]) {
  final age = (now ?? DateTime.now()).difference(time);
  if (age.inMinutes < 1) return 'just now';
  if (age.inHours < 1) return '${age.inMinutes} min ago';
  if (age.inDays < 1) return '${age.inHours} h ago';
  return '${age.inDays} d ago';
}

/// The colour of a status badge: the pins' colours, green for fixed (no pin) and grey for rejected.
Color statusChipColor(String status) => statusColors[status] ?? (status == 'fixed' ? const Color(0xFF41755E) : muted);

/// A badge in the status colour: soft fill, matching text.
class StatusChip extends StatelessWidget {
  const StatusChip(this.status, {super.key});

  final String status;

  @override
  Widget build(BuildContext context) {
    final color = statusChipColor(status);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: const BorderRadius.all(Radius.circular(4)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
        child: Text(
          statusLabels[status] ?? status,
          style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: color),
        ),
      ),
    );
  }
}

class _ReportCard extends StatelessWidget {
  const _ReportCard(this.report, {this.mine = false});

  final Report report;
  final bool mine; // a ticket this phone filed: shows its ID and what the city said about it

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: EdgeInsets.fromLTRB(20, 0, 20, 20 + MediaQuery.paddingOf(context).bottom),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (report.isSos)
            const _SosClip() // an SOS has a video, kept on the server, not a photo
          else
            ClipRRect(
            borderRadius: radiusChip,
            child: ColoredBox(
              color: paper,
              child: SizedBox(
                height: 280,
                width: double.infinity,
                child: Image.network(
                  '${api.base}${report.photoUrl}',
                  fit: BoxFit.cover,
                  semanticLabel: 'Photo of the report',
                  loadingBuilder: (_, image, progress) => progress == null
                      ? image
                      : Center(
                          child: CircularProgressIndicator(
                            value: progress.expectedTotalBytes == null
                                ? null
                                : progress.cumulativeBytesLoaded / progress.expectedTotalBytes!,
                          ),
                        ),
                  errorBuilder: (_, _, _) => const Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.broken_image_outlined, color: muted),
                        SizedBox(height: 6),
                        Text("Couldn't load the photo", style: TextStyle(fontSize: 12, color: muted)),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: Text(
                  report.label,
                  style: const TextStyle(fontFamily: serif, fontSize: 22, fontWeight: FontWeight.w500),
                ),
              ),
              StatusChip(report.status),
            ],
          ),
          const SizedBox(height: 4),
          Text(ago(report.createdAt), style: const TextStyle(fontSize: 12, color: muted)),
          if (report.note.isNotEmpty) ...[const SizedBox(height: 10), Text(report.note)],
          if (mine) ...[
            const SizedBox(height: 14),
            Text(report.code, style: const TextStyle(fontSize: 12, color: muted, letterSpacing: 0.3)),
            const SizedBox(height: 6),
            Text(ticketMessage(report), style: const TextStyle(fontSize: 14)),
            for (final n in ticketNotes(report)) ...[
              const SizedBox(height: 10),
              Text(n.label, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: muted)),
              const SizedBox(height: 2),
              Text(n.text),
            ],
          ],
        ],
      ),
    );
  }
}

/// Where an SOS's photo would be: it has no photo, only the video the city has.
class _SosClip extends StatelessWidget {
  const _SosClip();

  @override
  Widget build(BuildContext context) {
    return const ClipRRect(
      borderRadius: radiusChip,
      child: ColoredBox(
        color: paper,
        child: SizedBox(
          height: 140,
          width: double.infinity,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.videocam_outlined, color: sosRed, size: 36),
              SizedBox(height: 6),
              Text('SOS video sent to the city', style: TextStyle(fontSize: 13, color: muted)),
            ],
          ),
        ),
      ),
    );
  }
}
