// The suggested ways to get there: one tile per option with its minutes, arrival time, walking, the leg strip,
// and a badge on the quickest. Tapping a tile picks it, and the map draws it.
import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../state/trip_state.dart';
import '../../theme.dart';
import '../transfer_walk/route_card.dart' show durationLabel;
import 'leg_strip.dart';

/// "10:33 PM", "12:05 AM".
String arrivalLabel(DateTime t) {
  final h = t.hour % 12 == 0 ? 12 : t.hour % 12;
  return '$h:${t.minute.toString().padLeft(2, '0')} ${t.hour < 12 ? 'AM' : 'PM'}';
}

class CommuteList extends StatelessWidget {
  const CommuteList({super.key, required this.trip, this.now = DateTime.now});

  final TripState trip;
  final DateTime Function() now; // when "Arrive at" counts from: the moment this builds

  @override
  Widget build(BuildContext context) => ListenableBuilder(listenable: trip, builder: (context, _) => _build());

  Widget _build() {
    final options = trip.commute;
    if (options.isEmpty) {
      final text =
          trip.commuteError ??
          (trip.planned && !trip.loading
              ? 'No ride found near both ends of this trip. Try Walk.'
              : trip.planned
              ? 'Finding ways to get there…'
              : 'Waiting for your location…');
      return Text(text, style: TextStyle(fontSize: 12, color: trip.commuteError == null ? muted : warn));
    }
    final start = now();
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          '${options.length} suggested route${options.length == 1 ? '' : 's'}',
          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 6),
        ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 280),
          child: ListView.separated(
            shrinkWrap: true,
            padding: EdgeInsets.zero,
            itemCount: options.length,
            separatorBuilder: (_, _) => const SizedBox(height: 6),
            itemBuilder: (_, i) => _Tile(
              option: options[i],
              arrive: start.add(Duration(seconds: options[i].totalS.round())),
              selected: i == trip.selected,
              onTap: () => trip.select(i),
            ),
          ),
        ),
        const SizedBox(height: 6),
        const Text('Ride times are estimates.', style: TextStyle(fontSize: 11, color: muted)),
      ],
    );
  }
}

class _Tile extends StatelessWidget {
  const _Tile({required this.option, required this.arrive, required this.selected, required this.onTap});

  final CommuteOption option;
  final DateTime arrive;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      child: Material(
        color: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: radiusButton,
          side: BorderSide(color: selected ? navy : hairline, width: selected ? 1.5 : 1),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.baseline,
                  textBaseline: TextBaseline.alphabetic,
                  children: [
                    Text(
                      durationLabel(option.totalS),
                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Arrive at ${arrivalLabel(arrive)}',
                        style: const TextStyle(fontSize: 12, color: muted),
                      ),
                    ),
                    Text('${durationLabel(option.walkS)} walk', style: const TextStyle(fontSize: 12)),
                  ],
                ),
                const SizedBox(height: 8),
                LegStrip(legs: option.legs),
                if (option.isEarliest) ...[
                  const SizedBox(height: 8),
                  const Align(alignment: Alignment.centerRight, child: _Badge('Earliest arrival')),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(color: paper, borderRadius: radiusButton),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        child: Text(text, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w500)),
      ),
    );
  }
}
