// Fastest ⇄ Walkable ⇄ Accessible: three segments, each with that mode's walking time under its name.
import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../state/trip_state.dart';
import '../../theme.dart';
import 'route_card.dart' show durationLabel;

class ModeToggle extends StatelessWidget {
  const ModeToggle({super.key, required this.trip});

  final TripState trip;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (final MapEntry(key: mode, value: label) in routeModes.entries)
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(right: mode == routeModes.keys.last ? 0 : 6),
              child: _Segment(
                label: label,
                // The time once it is known; "–" when this mode has no route; "…" while it is on its way.
                detail: switch (mode == 'fastest' ? trip.fastestRoute : trip.routes[mode]) {
                  final r? => durationLabel(r.durationS),
                  null => trip.errors.containsKey(mode) || !trip.loading ? '–' : '…',
                },
                selected: trip.mode == mode,
                onTap: () => trip.setMode(mode),
              ),
            ),
          ),
      ],
    );
  }
}

class _Segment extends StatelessWidget {
  const _Segment({required this.label, required this.detail, required this.selected, required this.onTap});

  final String label;
  final String detail;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected ? paper : ink;
    return Semantics(
      button: true,
      selected: selected,
      label: '$label, $detail',
      onTap: onTap, // excludeSemantics drops the InkWell's own tap action
      excludeSemantics: true,
      child: Material(
        color: selected ? navy : Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: radiusButton,
          side: BorderSide(color: selected ? navy : hairline),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  label,
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: color),
                ),
                const SizedBox(height: 2),
                Text(detail, style: TextStyle(fontSize: 11, color: color)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
