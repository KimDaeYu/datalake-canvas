import { createContext } from "react";
import type { NodeResult } from "../types";

/** Latest run results keyed by node id, so node components can show their status. */
export const RunContext = createContext<Record<string, NodeResult>>({});
