import manifest from "../../../../public/data/data-manifest.json";

export const dynamic = "force-static";

export function GET() {
  return Response.json({
    status: "ok",
    version: "0.1.0",
    dataVersion: manifest.version,
    stage: manifest.stage,
  });
}
