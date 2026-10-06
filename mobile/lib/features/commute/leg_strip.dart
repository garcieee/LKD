// The trip at a glance, like a transit app's route row: an icon per leg, then a bar whose stretches are as long
// as the legs take. Walking is a thin grey line, a ride a thick navy one.
import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../theme.dart';

IconData legIcon(String kind) => switch (kind) {
  'walk' => Icons.directions_walk,
  'uv_express' => Icons.airport_shuttle,
  'mrt3' || 'lrt1' => Icons.train,
  _ => Icons.directions_bus, // jeepney, city bus, P2P bus
};

class LegStrip extends StatelessWidget {
  const LegStrip({super.key, required this.legs});

  final List<CommuteLeg> legs;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Wrap(
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: 4,
          runSpacing: 2,
          children: [
            for (var i = 0; i < legs.length; i++) ...[
              if (i > 0) const Icon(Icons.chevron_right, size: 16, color: muted),
              Icon(legIcon(legs[i].kind), size: 18, color: navy),
              if (!legs[i].isWalk)
                Text(
                  hubModeLabels[legs[i].kind] ?? legs[i].kind,
                  style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                ),
            ],
          ],
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            for (final leg in legs)
              Expanded(
                // A leg is never so short it vanishes.
                flex: leg.durationS.round().clamp(30, 1 << 30),
                child: Container(
                  height: leg.isWalk ? 2 : 5,
                  margin: const EdgeInsets.symmetric(horizontal: 1),
                  decoration: BoxDecoration(
                    color: leg.isWalk ? edgeStrong : navy,
                    borderRadius: const BorderRadius.all(Radius.circular(3)),
                  ),
                ),
              ),
          ],
        ),
      ],
    );
  }
}
