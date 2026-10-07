// The two cards while the trip is on. NavBanner, at the top: the next turn and how far away it is (or, where a leg
// has no turns, the leg the user is on and what is left of it), the street they are on, and what comes next.
// NavPanel, at the bottom: when they will arrive, the time and distance left, and a way to end the trip.
// Fed by TripState.update from the live GPS fixes.
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

const _radiusBanner = BorderRadius.all(Radius.circular(22));
const _stripNavy = Color(0xFF2E3D5E); // the banner's second line, a step lighter than navy
const _amber = Color(0xFFE9C98C); // warn, light enough to read on navy

class NavBanner extends StatelessWidget {
  const NavBanner({super.key, required this.trip});

  final TripState trip;

  @override
  Widget build(BuildContext context) => ListenableBuilder(listenable: trip, builder: (context, _) => _body());

  Widget _body() {
    final legs = trip.legs, p = trip.progress;
    if (p == null || p.leg >= legs.length) {
      return _Banner(
        icon: Icons.my_location,
        title: 'Finding your position…',
        subtitle: 'Trip to ${trip.destination?.label ?? ''}',
      );
    }
    if (p.arrived) {
      return _Banner(icon: Icons.flag, title: "You've arrived", subtitle: trip.destination?.label ?? '');
    }
    final leg = legs[p.leg], turn = p.turn, turnIn = p.turnInM;
    final next = p.leg + 1 < legs.length ? legs[p.leg + 1] : null;
    // The server's "Arrive at your destination" is only true on the last leg; on the others the leg ends at a hub.
    final lastLeg = next == null;
    final title = turn == null
        ? legTitle(leg)
        : turn.type == 10
        ? (lastLeg ? 'Arrive at ${trip.destination?.label ?? 'your destination'}' : legTitle(leg))
        : turn.text;
    final street = p.street.isEmpty ? '' : ' · on ${p.street}';
    return _Banner(
      icon: turn == null ? legIcon(leg.kind) : turnIcon(turn.type),
      iconSize: turn == null ? 32 : 40,
      title: title,
      subtitle: turn == null || turnIn == null
          ? '${distanceLabel(p.legLeftM)} left on this leg'
          : 'In ${distanceLabel(turnIn)}$street',
      strip: p.offRoute
          ? (
              icon: Icons.wrong_location_outlined,
              text: trip.rerouting
                  ? 'Off route · finding a new way…'
                  : 'Off route: ${distanceLabel(p.offM)} from the path',
              color: _amber,
            )
          : next == null
          ? null
          : (icon: legIcon(next.kind), text: 'Then: ${legTitle(next)}', color: Colors.white70),
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner({required this.icon, required this.title, required this.subtitle, this.iconSize = 32, this.strip});

  final IconData icon;
  final double iconSize;
  final String title;
  final String subtitle;
  final ({IconData icon, String text, Color color})? strip;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        borderRadius: _radiusBanner,
        boxShadow: [BoxShadow(color: Color(0x2959534E), blurRadius: 18, offset: Offset(0, 4))],
      ),
      child: Material(
        color: navy,
        shape: const RoundedRectangleBorder(borderRadius: _radiusBanner),
        clipBehavior: Clip.antiAlias,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
              child: Row(
                children: [
                  Icon(icon, color: paper, size: iconSize),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600, color: paper, height: 1.15),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          subtitle,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 13, color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            if (strip case final st?)
              Container(
                color: _stripNavy,
                padding: const EdgeInsets.fromLTRB(16, 9, 16, 10),
                child: Row(
                  children: [
                    Icon(st.icon, size: 18, color: st.color),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        st.text,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontSize: 13, color: st.color),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class NavPanel extends StatelessWidget {
  const NavPanel({super.key, required this.trip, this.now = DateTime.now});

  final TripState trip;
  final DateTime Function() now; // when "arrival" counts from: the moment this builds

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: trip,
      builder: (context, _) {
        final p = trip.progress;
        final onTrip = p != null && p.leg < trip.legs.length && !p.arrived;
        final eta = onTrip ? now().add(Duration(seconds: p.leftS.round())) : null;
        return ChipCard(
          padding: const EdgeInsets.fromLTRB(12, 14, 12, 4),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (eta != null)
                Row(
                  children: [
                    _Stat(arrivalLabel(eta), 'arrival'),
                    _Stat(durationLabel(p!.leftS), 'left'),
                    _Stat(distanceLabel(p.leftM), 'to go'),
                  ],
                ),
              TextButton(onPressed: trip.end, child: Text(p != null && p.arrived ? 'Done' : 'End trip')),
            ],
          ),
        );
      },
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat(this.value, this.caption);

  final String value;
  final String caption;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        children: [
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(value, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w600)),
          ),
          Text(caption, style: const TextStyle(fontSize: 13, color: muted)),
        ],
      ),
    );
  }
}
