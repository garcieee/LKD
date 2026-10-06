// The "Traffic flow" panel over the map: layer switch, refresh time, refresh button. No legend on mobile.
// Copy from dashboard/src/App.tsx.
import 'package:flutter/material.dart';

import '../config/env.dart';
import '../state/layers_state.dart';
import '../theme.dart';

class LayerSheet extends StatelessWidget {
  const LayerSheet({super.key, required this.layers, this.legend = const []});

  final LayersState layers;
  final List<({Color color, String label})> legend; // the transit hubs' colours (layers/hubs_layer.dart)

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: layers,
      builder: (context, _) => ChipCard(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: const Text(
                'Transit terminals and stops',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
              ),
              value: layers.hubsOn,
              onChanged: layers.setHubs,
            ),
            if (layers.hubsOn && legend.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Wrap(
                  spacing: 12,
                  runSpacing: 4,
                  children: [
                    for (final e in legend)
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            width: 10,
                            height: 10,
                            decoration: BoxDecoration(color: e.color, shape: BoxShape.circle),
                          ),
                          const SizedBox(width: 5),
                          Text(e.label, style: const TextStyle(fontSize: 11, color: muted)),
                        ],
                      ),
                  ],
                ),
              ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: const Text(
                'Traffic flow',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
              ),
              value: layers.congestionOn,
              onChanged: layers.setCongestion,
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: const Text(
                '3D map',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
              ),
              value: layers.threeD,
              onChanged: layers.setThreeD,
            ),
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Updated ${_clock(layers.stamp)}',
                    style: const TextStyle(fontSize: 12, color: muted),
                  ),
                ),
                OutlinedButton(onPressed: layers.refresh, child: const Text('Refresh now')),
              ],
            ),
            if (Env.tomtomKey.isEmpty)
              const Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text(
                  'No TomTom key. Set TOMTOM_API_KEY in env.json.',
                  style: TextStyle(fontSize: 12, color: warn),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

// "2026-10-06 14:32:08.123" -> "14:32:08" (local time)
String _clock(DateTime d) => d.toString().substring(11, 19);
