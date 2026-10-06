// The card while the trip is on: the next turn and how far away it is (or, where a leg has no turns, the leg the
// user is on and what is left of it), the street they are on, what is left of the trip, when they will arrive, and
// a way to end it. Fed by TripState.update from the live GPS fixes.
import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../state/trip_state.dart';
import '../../theme.dart';
import '../commute/commute_list.dart' show arrivalLabel;
import '../commute/leg_strip.dart' show legIcon;
import '../transfer_walk/route_card.dart' show distanceLabel, durationLabel;

/// "Walk to Ayala Terminal", "City bus: Ayala Terminal to Dian".
String legTitle(CommuteLeg leg) => leg.isWalk ? leg.label : '${hubModeLabels[leg.kind] ?? leg.kind}: ${leg.label}';

/// The glyph for one of ORS's turn codes (see RouteStep.type): 0 left, 1 right, 2 sharp left, 3 sharp right,
/// 4 slight left, 5 slight right, 6 straight, 7 roundabout in, 8 out, 9 u-turn, 10 arrive, 11 depart, 12 keep left,
/// 13 keep right.
IconData turnIcon(int type) => switch (type) {
  0 => Icons.turn_left,
  1 => Icons.turn_right,
  2 => Icons.turn_sharp_left,
  3 => Icons.turn_sharp_right,
  4 => Icons.turn_slight_left,
  5 => Icons.turn_slight_right,
  7 || 8 => Icons.roundabout_right,
  9 => Icons.u_turn_left,
  10 => Icons.flag,
  12 => Icons.fork_left,
  13 => Icons.fork_right,
  _ => Icons.straight, // straight on, and heading off
};

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
    final legs = trip.legs, p = trip.progress;
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
    final leg = legs[p.leg], turn = p.turn, turnIn = p.turnInM;
    final eta = now().add(Duration(seconds: p.leftS.round()));
    final next = p.leg + 1 < legs.length ? legs[p.leg + 1] : null;
    // The server's "Arrive at your destination" is only true on the last leg; on the others the leg ends at a hub.
    final lastLeg = next == null;
    final title = turn == null
        ? legTitle(leg)
        : turn.type == 10
        ? (lastLeg ? 'Arrive at ${trip.destination?.label ?? 'your destination'}' : legTitle(leg))
        : turn.text;
    final street = p.street.isEmpty ? '' : ' · on ${p.street}';
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _Row(
          icon: turn == null ? legIcon(leg.kind) : turnIcon(turn.type),
          iconSize: turn == null ? 24 : 32,
          title: title,
          subtitle: turn == null || turnIn == null
              ? '${distanceLabel(p.legLeftM)} left on this leg'
              : 'In ${distanceLabel(turnIn)}$street',
          action: _End(trip, 'End trip'),
        ),
        const SizedBox(height: 8),
        Text(
          '${durationLabel(p.leftS)} · ${distanceLabel(p.leftM)} left · arrive at ${arrivalLabel(eta)}',
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
        if (p.offRoute) ...[
          const SizedBox(height: 2),
          Text(
            trip.rerouting ? 'Off route · finding a new way…' : 'Off route: ${distanceLabel(p.offM)} from the path',
            style: const TextStyle(fontSize: 12, color: warn),
          ),
        ] else if (next != null) ...[
          const SizedBox(height: 2),
          Text('Then: ${legTitle(next)}', style: const TextStyle(fontSize: 12, color: muted)),
        ],
      ],
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.action,
    this.iconSize = 24,
  });

  final IconData icon;
  final double iconSize;
  final String title;
  final String subtitle;
  final Widget action;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: navy, size: iconSize),
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
