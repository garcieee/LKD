// LAYER REGISTRY (mobile): the one list every switch reads from.
// widgets/layer_sheet.dart and widgets/floating_toolbar.dart both render from it.
//
//   id          label                      default
//   reports     Reports nearby             on
//   hubs        Transit hubs               on
//   routes      Fastest / Walkable lines   on (drawn once a route is requested)
//   congestion  Traffic (TomTom)           off
//   sidewalks   Sidewalk coverage (OSM)    off
//
// Route mode is a separate toggle: Fastest, Walkable or Accessible
// (features/transfer_walk/mode_toggle.dart).
//
// Stub: no logic until kickoff (Tue 1:00 PM).
