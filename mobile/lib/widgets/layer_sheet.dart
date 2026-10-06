// The "Traffic flow" panel over the map: layer switch, refresh time, refresh button, legend.
// Copy and colours from dashboard/src/App.tsx and dashboard/src/panels/Legend.tsx.
import 'package:flutter/material.dart';

import '../config/env.dart';
import '../state/layers_state.dart';
import '../theme.dart';

const _small = TextStyle(fontSize: 10, color: muted);

class LayerSheet extends StatelessWidget {
  const LayerSheet({super.key, required this.layers});

  final LayersState layers;

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
                'Traffic flow',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
              ),
              value: layers.congestionOn,
              onChanged: layers.setCongestion,
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
            const SizedBox(height: 12),
            // The map's line colours (_ramp in layers/congestion_layer.dart), free flow on the left.
            const DecoratedBox(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.all(Radius.circular(999)),
                gradient: LinearGradient(
                  colors: [Color(0xFF2ECC71), Color(0xFFF7D154), Color(0xFFF28C28), Color(0xFFE54B4B)],
                  stops: [0, 0.33, 0.67, 1],
                ),
              ),
              child: SizedBox(height: 8),
            ),
            const SizedBox(height: 6),
            const Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [Text('Free flow', style: _small), Text('Standstill', style: _small)],
            ),
            const SizedBox(height: 8),
            const Text('Speed vs free flow · Traffic © TomTom', style: _small),
          ],
        ),
      ),
    );
  }
}

// "2026-10-06 14:32:08.123" -> "14:32:08" (local time)
String _clock(DateTime d) => d.toString().substring(11, 19);
