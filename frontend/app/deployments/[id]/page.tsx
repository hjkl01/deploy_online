"use client";

import {useEffect, useState} from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export default function Page({params}: {params: Promise<{id: string}>}) {
  const [id, setId] = useState("");
  const [logs, setLogs] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    let socket: WebSocket | undefined;
    let cancelled = false;

    params.then(({id: deploymentId}) => {
      if (cancelled) return;
      setId(deploymentId);

      fetch(API + "/api/deployments/" + deploymentId + "/logs", {credentials: "include"})
        .then((r) => r.json())
        .then((data) => setLogs(data.map((item: any) => item.message).join("")));

      fetch(API + "/api/deployments/" + deploymentId, {credentials: "include"})
        .then((r) => r.json())
        .then((data) => setStatus(data.status));

      socket = new WebSocket(WS + "/ws/deployments/" + deploymentId);
      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "snapshot") setLogs(data.logs.map((item: any) => item.message).join(""));
        if (data.type === "log") setLogs((value) => value + data.message);
      };
    });

    return () => {
      cancelled = true;
      socket?.close();
    };
  }, [params]);

  return (
    <main className="wrap">
      <h1>部署 #{id} {status}</h1>
      <pre>{logs}</pre>
      <a href="/">← 返回</a>
    </main>
  );
}
