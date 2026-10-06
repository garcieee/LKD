// Transit hubs in the app: the card that opens on a hub (with "Walk here"), and the list of the ones nearest the user.
import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../layers/hubs_layer.dart' show hubColor;
import '../../theme.dart';
import '../report/ar_math.dart' show distanceM;
import 'route_card.dart' show distanceLabel;

typedef Where = ({double lat, double lng});

/// The hubs closest to [from], nearest first, with their distance in metres. Terminals and train stations only
/// unless [withStops]. Without a position: alphabetical, distance null.
List<({Hub hub, double? metres})> nearestHubs(List<Hub> hubs, Where? from, {int limit = 8, bool withStops = false}) {
  final pool = [
    for (final h in hubs)
      if (withStops || h.kind != 'stop') h,
  ];
  if (from == null) {
    pool.sort((a, b) => a.name.compareTo(b.name));
    return [for (final h in pool.take(limit)) (hub: h, metres: null)];
  }
  final rows = [for (final h in pool) (hub: h, metres: distanceM(from.lat, from.lng, h.lat, h.lng))];
  rows.sort((a, b) => a.metres.compareTo(b.metres));
  return rows.take(limit).toList();
}

/// "About ±80 m": how far off the dot on the map might be. The positions come from the study's maps, not a survey.
String positionNote(Hub h) => 'Position estimated from the study map, about ±${h.errorM} m.';

Future<void> showHubSheet(BuildContext context, Hub hub, {Where? from, required void Function(Hub) onWalk}) =>
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      useSafeArea: true,
      builder: (sheet) => _HubCard(
        hub,
        metres: from == null ? null : distanceM(from.lat, from.lng, hub.lat, hub.lng),
        onWalk: () {
          Navigator.pop(sheet);
          onWalk(hub);
        },
      ),
    );

/// The terminals nearest the user. Tapping one opens its card.
Future<void> showNearbyHubs(
  BuildContext context,
  List<Hub> hubs, {
  Where? from,
  required void Function(Hub) onWalk,
}) => showModalBottomSheet<void>(
  context: context,
  showDragHandle: true,
  isScrollControlled: true,
  useSafeArea: true,
  builder: (sheet) {
    final rows = nearestHubs(hubs, from);
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, 12 + MediaQuery.paddingOf(sheet).bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Transit near you', style: TextStyle(fontFamily: serif, fontSize: 22, fontWeight: FontWeight.w500)),
          const SizedBox(height: 2),
          Text(
            from == null ? 'Location is off, so these are listed by name.' : 'Terminals and stations, nearest first.',
            style: const TextStyle(fontSize: 12, color: muted),
          ),
          const SizedBox(height: 6),
          if (rows.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: Text('No transit data yet. Check the connection.', style: TextStyle(color: muted)),
            )
          else
            Flexible(
              child: ListView(
                shrinkWrap: true,
                children: [
                  for (final r in rows)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(
                        r.hub.isStation ? Icons.train_outlined : Icons.directions_bus_outlined,
                        color: hubColor(r.hub),
                      ),
                      title: Text(r.hub.name),
                      subtitle: Text(r.hub.modesLabel, style: const TextStyle(fontSize: 12)),
                      trailing: r.metres == null ? null : Text(distanceLabel(r.metres!)),
                      onTap: () {
                        Navigator.pop(sheet);
                        showHubSheet(context, r.hub, from: from, onWalk: onWalk);
                      },
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  },
);

class _HubCard extends StatelessWidget {
  const _HubCard(this.hub, {required this.metres, required this.onWalk});

  final Hub hub;
  final double? metres;
  final VoidCallback onWalk;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, 20 + MediaQuery.paddingOf(context).bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(hub.name, style: const TextStyle(fontFamily: serif, fontSize: 22, fontWeight: FontWeight.w500)),
          const SizedBox(height: 4),
          Text(
            '${hub.kindLabel} · ${hub.modesLabel}',
            style: const TextStyle(fontSize: 13),
          ),
          if (metres != null) ...[
            const SizedBox(height: 2),
            Text('${distanceLabel(metres!)} from you', style: const TextStyle(fontSize: 13, color: muted)),
          ],
          const SizedBox(height: 6),
          Text(positionNote(hub), style: const TextStyle(fontSize: 12, color: muted)),
          const SizedBox(height: 14),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: onWalk,
              icon: const Icon(Icons.directions_walk, size: 20),
              label: const Text('Walk here'),
              style: FilledButton.styleFrom(
                minimumSize: const Size(0, 48),
                shape: const RoundedRectangleBorder(borderRadius: radiusChip),
                textStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
