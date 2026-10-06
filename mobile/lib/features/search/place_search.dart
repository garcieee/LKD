// Search-as-you-type for the destination field: waits for a pause in typing, asks the server, and
// drops any answer that a newer keystroke has made stale. UI-free so it can be tested (place_search_test.dart).
import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../api/api_client.dart';

typedef Near = ({double lat, double lng});
typedef SearchFn = Future<List<Place>> Function(String text, Near? near);

/// Fewer characters than this is not searched: "ay" would match half the city, and each search is
/// one call against the server's daily OpenRouteService allowance.
const minSearchChars = 3;

class PlaceSearch extends ChangeNotifier {
  PlaceSearch(this._search, {this.delay = const Duration(milliseconds: 350)});

  final SearchFn _search;
  final Duration delay; // the pause in typing that starts a search

  /// null: nothing to show yet. Empty: searched, found nothing.
  List<Place>? results;
  bool loading = false;
  String? error; // fit to show, from ApiException

  Timer? _timer;
  int _round = 0; // bumped on every keystroke; an answer from an older round is dropped
  bool _disposed = false;

  void onChanged(String text, {Near? near}) {
    _timer?.cancel();
    final round = ++_round;
    final q = text.trim();
    if (q.length < minSearchChars) {
      results = null;
      loading = false;
      error = null;
      return notifyListeners();
    }
    loading = true;
    error = null;
    notifyListeners();
    _timer = Timer(delay, () async {
      List<Place>? found;
      String? failed;
      try {
        found = await _search(q, near);
      } on ApiException catch (e) {
        failed = e.message;
      }
      if (round != _round || _disposed) return;
      results = failed == null ? found : null;
      error = failed;
      loading = false;
      notifyListeners();
    });
  }

  /// Forgets the query and its results.
  void clear() => onChanged('');

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    super.dispose();
  }
}
