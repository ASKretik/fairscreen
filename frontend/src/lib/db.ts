// Firestore lives in its own module so it is only loaded by the signed-in pages,
// keeping the landing page and /demo light.
import { getFirestore } from "firebase/firestore";
import { app } from "./firebase";

export const db = app ? getFirestore(app) : null;
