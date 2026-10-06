// Bottom-left legend for the congestion colours.
export default function Legend() {
  return (
    <div className="panel legend">
      <div className="panel-title">Traffic flow</div>
      <div className="legend-bar" />
      <div className="legend-ends">
        <span>Free flow</span>
        <span>Standstill</span>
      </div>
      <div className="legend-note">Speed against free-flow speed · TomTom</div>
    </div>
  );
}
