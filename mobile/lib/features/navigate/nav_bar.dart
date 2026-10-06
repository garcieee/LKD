// The card while the trip is on: the leg the user is on, what is left of it and of the trip, when they will
// arrive, and a way to end it. Fed by TripState.update from the live GPS fixes.
import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../state/trip_state.dart';
import '../../theme.dart';
import '../commute/commute_list.dart' show arrivalLabel;
import '../commute/leg_strip.dart' show legIcon;
import '../transfer_walk/route_card.dart' show distanceLabel, durationLabel;

/// "Walk to Ayala Terminal", "City bus: Ayala Terminal to Dian".
String legTitle(CommuteLeg leg) => leg.isWalk ? leg.label : '${hubModeLabels[leg.kind] ?? leg.kind}: ${leg.label}';

class NavBar extends StatelessWidget {
  const NavBar({super.key, required this.trip, this.now = DateTime.now});

  final TripState trip;
  final DateTime Function() now; // when "Arrive at" counts from: the moment this builds

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: trip,
      builder: (context, _) => ChipCard(padding: const EdgeInsets.all(12), child: _body()),
    );
  }

  Widget _body() {
    final legs = trip.activeLegs, p = trip.progress;
    if (p == null || p.leg >= legs.length) {
      return _Row(
        icon: Icons.my_location,
        title: 'Finding your position…',
        subtitle: 'Trip to ${trip.destination?.label ?? ''}',
        action: _End(trip, 'End trip'),
      );
    }
    if (p.arrived) {
      return _Row(
        icon: Icons.flag,
        title: "You've arrived",
        subtitle: trip.destination?.label ?? '',
        action: _End(trip, 'Done'),
      );
    }
    final leg = legs[p.leg];
    final eta = now().add(Duration(seconds: p.leftS.round()));
    final next = p.leg + 1 < legs.length ? legs[p.leg + 1] : null;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _Row(
          icon: legIcon(leg.kind),
          title: legTitle(leg),
          subtitle: '${distanceLabel(p.legLeftM)} left on this leg',
          action: _End(trip, 'End trip'),
        ),
        const SizedBox(height: 8),
        Text(
          '${durationLabel(p.leftS)} left · arrive at ${arrivalLabel(eta)}',
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
        if (p.offRoute) ...[
          const SizedBox(height: 2),
          Text('Off route: ${distanceLabel(p.offM)} from the path', style: const TextStyle(fontSize: 12, color: warn)),
        ] else if (next != null) ...[
          const SizedBox(height: 2),
          Text('Then: ${legTitle(next)}', style: const TextStyle(fontSize: 12, color: muted)),
        ],
      ],
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({required this.icon, required this.title, required this.subtitle, required this.action});

  final IconData icon;
  final String title;
  final String subtitle;
  final Widget action;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: navy),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
              ),
              Text(
                subtitle,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 12, color: muted),
              ),
            ],
          ),
        ),
        action,
      ],
    );
  }
}

class _End extends StatelessWidget {
  const _End(this.trip, this.label);

  final TripState trip;
  final String label;

  @override
  Widget build(BuildContext context) => TextButton(onPressed: trip.end, child: Text(label));
}
