// The "Traffic flow" panel over the map: layer switch, refresh time, refresh button. No legend on mobile.
// Copy from dashboard/src/App.tsx.
import 'package:flutter/material.dart';

import '../config/env.dart';
import '../state/layers_state.dart';
import '../theme.dart';

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
          ],
        ),
      ),
    );
  }
}

// "2026-10-06 14:32:08.123" -> "14:32:08" (local time)
String _clock(DateTime d) => d.toString().substring(11, 19);
