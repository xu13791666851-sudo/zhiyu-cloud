const { Client } = require("ssh2");
const path = require("path");

function putFile(ssh, local, remote) {
  return new Promise((resolve, reject) => {
    ssh.sftp((err, sftp) => {
      if (err) return reject(err);
      sftp.fastPut(local, remote, (err) => {
        sftp.end();
        if (err) return reject(err);
        resolve();
      });
    });
  });
}

function exec(ssh, cmd, timeout = 60000) {
  return new Promise((resolve, reject) => {
    ssh.exec(cmd, { timeout }, (err, stream) => {
      if (err) return reject(err);
      let stdout = "";
      let stderr = "";
      stream.on("data", (d) => (stdout += d));
      stream.stderr.on("data", (d) => (stderr += d));
      stream.on("close", () => resolve({ stdout, stderr }));
    });
  });
}

async function run() {
  const ssh = new Client();
  await new Promise((resolve, reject) => {
    ssh.on("ready", resolve).on("error", reject).connect({
      host: "43.138.213.164",
      port: 22,
      username: "ubuntu",
      password: "nx]Ee+w4*Nc5f8-",
    });
  });
  console.log("Connected!");

  // Check if zhiyu-app container exists
  console.log("[1] Checking container status...");
  const ps = await exec(ssh, "docker ps -a --filter name=zhiyu-app --format '{{.Status}} {{.Image}}'");
  console.log("  Container:", ps.stdout.trim() || "NOT FOUND");

  // Check available images
  console.log("[2] Checking available images...");
  const imgs = await exec(ssh, "docker images zhiyu --format '{{.Repository}}:{{.Tag}}'");
  console.log("  Images:", imgs.stdout.trim() || "NONE");

  // Upload fixed app.py
  console.log("[3] Uploading app.py...");
  await putFile(ssh, path.join(__dirname, "app.py"), "/tmp/app.py");
  console.log("  Uploaded.");

  // If container exists, just copy file and restart
  if (ps.stdout.trim()) {
    console.log("[4] Container exists, copying app.py and restarting...");
    await exec(ssh, "docker cp /tmp/app.py zhiyu-app:/app/app.py");
    await exec(ssh, "docker restart zhiyu-app");
    console.log("  Restarted.");
  } else {
    // Try to recreate from latest available image
    const imageTag = imgs.stdout.trim().split("\n").pop();
    if (imageTag) {
      console.log(`[4] Recreating container from ${imageTag}...`);
      await exec(ssh, `docker run -d --name zhiyu-app -p 8080:7860 --add-host=host.docker.internal:host-gateway -e HUNYUAN_API_KEY=sk-6aEJFYi6xHP00sLPhc0WBAcLES3PdIBmUCIdPQMymcJkSTtM ${imageTag}`);
      // Also copy fixed app.py
      await exec(ssh, "docker cp /tmp/app.py zhiyu-app:/app/app.py");
      await exec(ssh, "docker restart zhiyu-app");
      console.log("  Created and restarted.");
    } else {
      console.log("ERROR: No zhiyu images found. Need full rebuild.");
      ssh.end();
      return;
    }
  }

  // Wait for Gradio
  console.log("[5] Waiting 30s for Gradio...");
  await new Promise((res) => setTimeout(res, 30000));

  // Health check
  console.log("[6] Health check...");
  const chk = await exec(
    ssh,
    "docker exec zhiyu-app python3 -c \"import urllib.request; r=urllib.request.urlopen('http://localhost:7860/', timeout=10); print('HTTP', r.status)\" 2>&1"
  );
  console.log("  Result:", chk.stdout.trim() || chk.stderr.trim());

  if (chk.stdout.includes("200")) {
    console.log("\n✅ Back online! http://43.138.213.164:8080");
  } else {
    console.log("\n❌ Not ready. Checking logs...");
    const logs = await exec(ssh, "docker logs --tail 20 zhiyu-app 2>&1");
    console.log(logs.stdout.slice(-2000));
  }

  ssh.end();
}

run().catch((e) => console.error("ERROR:", e.message));
