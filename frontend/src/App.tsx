import { Routes, Route } from "react-router-dom";
import ProjectLayout from "./components/ProjectLayout";
import ProjectList from "./pages/ProjectList";
import Dashboard from "./pages/Dashboard";
import Preprocess from "./pages/Preprocess";
import Outline from "./pages/Outline";
import Settings from "./pages/Settings";
import Write from "./pages/Write";
import ChapterEditor from "./pages/ChapterEditor";
import Hooks from "./pages/Hooks";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ProjectList />} />
      <Route path="/project/:id" element={<ProjectLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="preprocess" element={<Preprocess />} />
        <Route path="outline" element={<Outline />} />
        <Route path="settings" element={<Settings />} />
        <Route path="write" element={<Write />} />
        <Route path="write/:ch" element={<ChapterEditor />} />
        <Route path="hooks" element={<Hooks />} />
      </Route>
    </Routes>
  );
}
