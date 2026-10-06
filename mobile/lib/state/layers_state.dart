// Which layers are on, and when the congestion layer was last refreshed.
// A plain ChangeNotifier: the map view and the layer sheet both listen to it.
import 'package:flutter/foundation.dart';

// ponytail: not remembered between launches (the dashboard does not either) and no registry,
// because there is one layer. Add shared_preferences and layers/layer_registry.dart with the second.
class LayersState extends ChangeNotifier {
  bool congestionOn = true; // on by default, as on the dashboard
  DateTime stamp = DateTime.now(); // last refresh; also the tile cache-buster

  void setCongestion(bool on) {
    congestionOn = on;
    if (on) stamp = DateTime.now(); // switching on fetches fresh tiles
    notifyListeners();
  }

  void refresh() {
    stamp = DateTime.now();
    notifyListeners();
  }
}
