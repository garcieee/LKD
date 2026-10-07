// The trip card over the map: Commute or Walk first, then the relevant options and Start.
import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../state/trip_state.dart';
import '../../theme.dart';
import '../commute/commute_list.dart';
import 'mode_toggle.dart';

/// "480 m", "1.2 km".
String distanceLabel(double metres) =>
    metres < 1000 ? '${metres.round()} m' : '${(metres / 1000).toStringAsFixed(1)} km';

/// "6 min", "1 h 5 min", "2 h". Never under a minute.
String durationLabel(double seconds) {
  final min = (seconds / 60).round();
  if (min < 1) return '1 min';
  if (min < 60) return '$min min';
  return min % 60 == 0 ? '${min ~/ 60} h' : '${min ~/ 60} h ${min % 60} min';
}

/// What the route does about unresolved reports. Walkable and Accessible steer around them; if they
/// could not (the server found no way around), say so rather than claim they did.
String hazardLabel(WalkRoute r) {
  final n = r.hazardIds.length;
  if (n == 0) return r.avoidsHazards ? 'Steers clear of reported hazards' : 'No reported hazards on this route';
  final noWayAround = r.mode != 'fastest' && !r.avoidsHazards;
  return 'Passes $n reported hazard${n == 1 ? '' : 's'}${noWayAround ? ' (no way around)' : ''}';
}

class RouteCard extends StatelessWidget {
  const RouteCard({super.key, required this.trip});

  final TripState trip;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: trip,
      builder: (context, _) {
        final route = trip.route, error = trip.error;
        return ChipCard(
          padding: const EdgeInsets.all(12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                trip.destination?.label ?? '',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 12, color: muted),
              ),
              const SizedBox(height: 8),
              if (trip.hasCommute) ...[_TripKindToggle(trip: trip), const SizedBox(height: 10)],
              if (trip.step == TripStep.commute) ...[
                CommuteList(trip: trip),
                if (!trip.commuteLoading &&
                    trip.commute.isEmpty &&
                    (trip.commuteMode != null || trip.commuteError != null)) ...[
                  const SizedBox(height: 4),
                  TextButton.icon(
                    onPressed: trip.backToWalk,
                    icon: const Icon(Icons.directions_walk, size: 18),
                    label: const Text('Walk instead'),
                  ),
                ],
                const SizedBox(height: 10),
                FilledButton.icon(
                  onPressed: trip.canStart ? trip.start : null,
                  style: FilledButton.styleFrom(shape: const RoundedRectangleBorder(borderRadius: radiusButton)),
                  icon: const Icon(Icons.navigation, size: 18),
                  label: const Text('Start trip'),
                ),
              ] else ...[
                const Text(
                  'Walking route',
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: muted),
                ),
                const SizedBox(height: 6),
                ModeToggle(trip: trip),
                const SizedBox(height: 10),
                if (route != null) ...[
                  Text(
                    '${distanceLabel(route.distanceM)} · ${durationLabel(route.durationS)}',
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    hazardLabel(route),
                    style: TextStyle(fontSize: 12, color: route.hazardIds.isEmpty ? muted : warn),
                  ),
                ] else if (error != null)
                  Text(error, style: const TextStyle(fontSize: 12, color: warn))
                else
                  Text(
                    trip.planned ? 'Finding the route…' : 'Waiting for your location…',
                    style: const TextStyle(fontSize: 12, color: muted),
                  ),
                const SizedBox(height: 10),
                FilledButton.icon(
                  onPressed: trip.canStart ? trip.start : null,
                  style: FilledButton.styleFrom(shape: const RoundedRectangleBorder(borderRadius: radiusButton)),
                  icon: const Icon(Icons.directions_walk, size: 18),
                  label: const Text('Start walking'),
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}

/// The first decision stays visible while either kind of route is being compared.
class _TripKindToggle extends StatelessWidget {
  const _TripKindToggle({required this.trip});

  final TripState trip;

  @override
  Widget build(BuildContext context) => SegmentedButton<TripStep>(
    segments: const [
      ButtonSegment(value: TripStep.commute, icon: Icon(Icons.directions_transit, size: 16), label: Text('Commute')),
      ButtonSegment(value: TripStep.walk, icon: Icon(Icons.directions_walk, size: 16), label: Text('Walk')),
    ],
    selected: {trip.step},
    showSelectedIcon: false,
    onSelectionChanged: (selected) {
      if (selected.single == TripStep.commute) {
        trip.toCommute();
      } else {
        trip.backToWalk();
      }
    },
    style: SegmentedButton.styleFrom(
      selectedBackgroundColor: navy,
      selectedForegroundColor: paper,
      foregroundColor: ink,
      side: const BorderSide(color: hairline),
    ),
  );
}
