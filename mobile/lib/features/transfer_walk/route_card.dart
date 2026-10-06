// The trip card over the map: where to, then either the suggested commutes or the walking routes (mode toggle,
// and what the chosen route is like: length, time, and how many reported hazards it still passes).
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
              if (trip.step == TripStep.commute) ...[
                _BackToWalk(trip: trip),
                const SizedBox(height: 6),
                CommuteList(trip: trip),
                const SizedBox(height: 10),
                FilledButton.icon(
                  onPressed: trip.canStart ? trip.start : null,
                  style: FilledButton.styleFrom(shape: const RoundedRectangleBorder(borderRadius: radiusButton)),
                  icon: const Icon(Icons.navigation, size: 18),
                  // With no ride to take, the trip is the walk alone.
                  label: Text(trip.option == null ? 'Start walking' : 'Start trip'),
                ),
              ] else ...[
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
                if (trip.hasCommute) ...[
                  const SizedBox(height: 10),
                  FilledButton(
                    onPressed: route == null ? null : trip.toCommute,
                    style: FilledButton.styleFrom(shape: const RoundedRectangleBorder(borderRadius: radiusButton)),
                    child: const Text('Next: ride options'),
                  ),
                ],
              ],
            ],
          ),
        );
      },
    );
  }
}

/// The way back to the walking comparison, naming the mode the commute's walking legs use.
class _BackToWalk extends StatelessWidget {
  const _BackToWalk({required this.trip});

  final TripState trip;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: TextButton.icon(
        onPressed: trip.backToWalk,
        icon: const Icon(Icons.arrow_back, size: 16),
        label: Text('Walking: ${routeModes[trip.mode]}'),
      ),
    );
  }
}
