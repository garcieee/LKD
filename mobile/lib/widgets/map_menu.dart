// The burger menu's sheet: how the map is drawn (Auto / 2D / 3D) and visible map details.
import 'package:flutter/material.dart';

import '../config/env.dart';
import '../state/layers_state.dart';
import '../theme.dart';

Future<void> showMapMenu(BuildContext context, LayersState layers) => showModalBottomSheet<void>(
  context: context,
  showDragHandle: true,
  isScrollControlled: true,
  useSafeArea: true,
  builder: (sheet) => ListenableBuilder(
    listenable: layers,
    builder: (context, _) => SingleChildScrollView(
      padding: EdgeInsets.fromLTRB(20, 0, 20, 20 + MediaQuery.paddingOf(sheet).bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Map type', style: TextStyle(fontFamily: serif, fontSize: 22, fontWeight: FontWeight.w500)),
          const SizedBox(height: 12),
          Row(
            children: [
              for (final (mode, icon, label) in const [
                (MapMode.auto, Icons.brightness_auto_outlined, 'Auto'),
                (MapMode.flat, Icons.map_outlined, '2D map'),
                (MapMode.tilted, Icons.view_in_ar_outlined, '3D map'),
              ])
                Expanded(child: _Tile(icon: icon, label: label, on: layers.mode == mode, onTap: () => layers.setMode(mode))),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Auto tilts the map into 3D while you are navigating.',
            style: const TextStyle(fontSize: 12, color: muted),
          ),
          const Divider(height: 28, color: hairline),
          const Text('Map details', style: TextStyle(fontFamily: serif, fontSize: 22, fontWeight: FontWeight.w500)),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Show tickets on map', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
            value: layers.ticketsOn,
            onChanged: layers.setTickets,
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Traffic flow', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
            subtitle: Env.tomtomKey.isEmpty
                ? const Text('No TomTom key. Set TOMTOM_API_KEY in env.json.', style: TextStyle(fontSize: 12, color: warn))
                : null,
            value: layers.congestionOn,
            onChanged: layers.setCongestion,
          ),
        ],
      ),
    ),
  ),
);

class _Tile extends StatelessWidget {
  const _Tile({required this.icon, required this.label, required this.on, required this.onTap});

  final IconData icon;
  final String label;
  final bool on;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: radiusChip,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4),
        child: Column(
          children: [
            Container(
              height: 64,
              decoration: BoxDecoration(
                borderRadius: radiusChip,
                color: paper,
                border: Border.all(color: on ? navy : hairline, width: on ? 2.5 : 1),
              ),
              child: Center(child: Icon(icon, size: 28, color: on ? navy : muted)),
            ),
            const SizedBox(height: 6),
            Text(
              label,
              style: TextStyle(fontSize: 13, fontWeight: on ? FontWeight.w700 : FontWeight.w400, color: on ? navy : ink),
            ),
          ],
        ),
      ),
    );
  }
}
