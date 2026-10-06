// "Where to?": the destination field at the top of the map, with suggestions under it.
// Typing searches (place_search.dart); picking a suggestion sets the trip's destination.
import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../state/trip_state.dart';
import '../../theme.dart';
import 'place_search.dart';

class PlaceSearchBar extends StatefulWidget {
  const PlaceSearchBar({super.key, required this.search, required this.trip, this.near});

  final PlaceSearch search;
  final TripState trip;
  final Near? Function()? near; // the user's position, to rank nearby places first

  @override
  State<PlaceSearchBar> createState() => _PlaceSearchBarState();
}

class _PlaceSearchBarState extends State<PlaceSearchBar> {
  final _text = TextEditingController();
  final _focus = FocusNode();
  bool _picked = false; // the text is a chosen place, not a query: no suggestions

  @override
  void initState() {
    super.initState();
    widget.trip.addListener(_followTrip);
  }

  // A destination set from elsewhere (a transit hub's "Walk here") shows in the field, and one cleared
  // from elsewhere empties it.
  void _followTrip() {
    final place = widget.trip.destination;
    if (place == null) {
      if (_picked) {
        _picked = false;
        _text.clear();
        setState(() {});
      }
    } else if (_text.text != place.label) {
      _picked = true;
      _text.text = place.label;
      widget.search.clear();
      setState(() {});
    }
  }

  @override
  void dispose() {
    widget.trip.removeListener(_followTrip);
    _text.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _typed(String text) {
    _picked = false;
    widget.search.onChanged(text, near: widget.near?.call());
    setState(() {}); // the clear button follows the text
  }

  void _pick(Place place) {
    _picked = true;
    _text.text = place.label;
    _focus.unfocus();
    widget.search.clear();
    widget.trip.setDestination(place, from: widget.near?.call());
  }

  void _clear() {
    _picked = false;
    _text.clear();
    widget.search.clear();
    widget.trip.clear();
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.search,
      builder: (context, _) {
        final s = widget.search;
        final hasText = _text.text.isNotEmpty;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            ChipCard(
              padding: EdgeInsets.zero,
              child: TextField(
                controller: _text,
                focusNode: _focus,
                onChanged: _typed,
                textInputAction: TextInputAction.search,
                style: const TextStyle(fontSize: 14),
                decoration: InputDecoration(
                  hintText: 'Where to?',
                  hintStyle: const TextStyle(color: muted),
                  border: InputBorder.none,
                  contentPadding: const EdgeInsets.symmetric(horizontal: 4, vertical: 14),
                  prefixIcon: const Icon(Icons.search, color: muted, size: 22),
                  suffixIcon: s.loading
                      ? const Padding(
                          padding: EdgeInsets.all(14),
                          child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
                        )
                      : hasText
                      ? IconButton(tooltip: 'Clear', onPressed: _clear, icon: const Icon(Icons.close, size: 20))
                      : null,
                ),
              ),
            ),
            if (!_picked && s.error != null) ...[
              const SizedBox(height: 8),
              ChipCard(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                child: Text(s.error!, style: const TextStyle(fontSize: 12, color: warn)),
              ),
            ] else if (!_picked && s.results != null) ...[
              const SizedBox(height: 8),
              ChipCard(
                padding: EdgeInsets.zero,
                child: s.results!.isEmpty
                    ? const Padding(
                        padding: EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                        child: Text('No places found in Makati.', style: TextStyle(fontSize: 13, color: muted)),
                      )
                    : Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          for (final p in s.results!)
                            ListTile(
                              dense: true,
                              leading: const Icon(Icons.place_outlined, size: 20, color: muted),
                              title: Text(p.label, maxLines: 2, overflow: TextOverflow.ellipsis),
                              onTap: () => _pick(p),
                            ),
                        ],
                      ),
              ),
            ],
          ],
        );
      },
    );
  }
}
