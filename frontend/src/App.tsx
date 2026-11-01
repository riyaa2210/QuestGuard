import { Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { EndpointsPage } from "@/pages/EndpointsPage";
import { EventsPage } from "@/pages/EventsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<EndpointsPage />} />
        <Route path="/events" element={<Navigate to="/" replace />} />
        <Route path="/endpoints/:endpointId" element={<EventsPage />} />
      </Route>
    </Routes>
  );
}
