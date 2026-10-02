    def _handle_flight_state(
        self,
        message: AirFlightStateMessage,
        event: ProtocolEvent | None,
    ) -> None:
        self._mark_mission_started("first_flight_state", message.time_ms)
        if self.state.mission_presentation.phase is MissionPhase.PRE_START:
            self.state.mission_presentation.phase = MissionPhase.MISSION_ACTIVE
        self._handle_sensor_message(message, event, source="FLIGHT_STATE")
        if self.state.mission_first_time_ms is None:
            self.state.mission_first_time_ms = message.time_ms
        self.state.latest_flight_time_ms = message.time_ms
        mission_time_s = max(
            0.0,
            (message.time_ms - self.state.mission_first_time_ms) / 1000.0,
        )
        self.state.live_plot.append(mission_time_s, message.vel_mps, message.pos_m)

        stats = event.packet_stats if event is not None else None
        if stats is None:
            stats = self._track_flight_packet(message.time_ms)
        self.state.received_flight_packets = int(stats["received_flight_packets"])
        self.state.estimated_lost_packets = int(stats["estimated_lost_packets"])
        self.state.expected_flight_packets = int(stats["expected_flight_packets"])
        self.state.packet_loss_rate = float(stats["packet_loss_rate"])
