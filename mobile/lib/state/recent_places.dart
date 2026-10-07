// The last few destinations picked, newest first, kept between launches.
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api_client.dart';

const _key = 'recent_places';
const maxRecents = 5;

class RecentPlaces extends ChangeNotifier {
  List<Place> places = const [];

  Future<void> load() async {
    try {
      final saved = (await SharedPreferences.getInstance()).getStringList(_key) ?? const [];
      places = [for (final s in saved) Place.fromJson(jsonDecode(s) as Map<String, dynamic>)];
      notifyListeners();
    } catch (e) {
      debugPrint('recent places: $e'); // no history is fine
    }
  }

  Future<void> add(Place p) async {
    places = [p, ...places.where((o) => o.label != p.label)].take(maxRecents).toList();
    notifyListeners();
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setStringList(_key, [
        for (final o in places) jsonEncode({'label': o.label, 'lat': o.lat, 'lng': o.lng}),
      ]);
    } catch (e) {
      debugPrint('recent places: $e');
    }
  }
}
