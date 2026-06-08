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

function exec(ssh, cmd, timeout = 300000) {
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

  // [1/4] Upload updated app.py
  console.log("[1/4] Uploading app.py...");
  await putFile(
    ssh,
    path.join(__dirname, "app.py"),
    "/home/ubuntu/zhiyu/app.py"
  );
  console.log("  Uploaded.");

  // [2/4] Stop and remove old container
  console.log("[2/4] Stopping old container...");
  await exec(ssh, "docker stop zhiyu-app 2>/dev/null; docker rm zhiyu-app 2>/dev/null");
  console.log("  Removed.");

  // [3/4] Build new image
  console.log("[3/4] Building zhiyu:v21 (this takes ~2min)...");
  const build = await exec(ssh, "cd /home/ubuntu/zhiyu && docker build --no-cache -t zhiyu:v21 . 2>&1", 180000);
  const buildLines = (build.stdout + build.stderr).split("\n").filter(l => l.includes("Step") || l.includes("Successfully"));
  buildLines.forEach(l => console.log("  " + l));

  // [4/4] Run new container
  console.log("[4/4] Starting new container...");
  await exec(ssh, `docker run -d --name zhiyu-app -p 8080:7860 --add-host=host.docker.internal:host-gateway -e HUNYUAN_API_KEY=sk-6aEJFYi6xHP00sLPhc0WBAcLES3PdIBmUCIdPQMymcJkSTtM zhiyu:v21`);
  console.log("  Started.");

  // Wait for Gradio to boot
  console.log("Waiting 30s for Gradio to start...");
  await new Promise((res) => setTimeout(res, 30000));

  // Health check
  console.log("Health check...");
  const chk = await exec(
    ssh,
    "docker exec zhiyu-app python3 -c \"import urllib.request; r=urllib.request.urlopen('http://localhost:7860/', timeout=10); print('HTTP', r.status)\" 2>&1"
  );
  console.log(chk.stdout || chk.stderr);

  if (chk.stdout.includes("HTTP 200")) {
    console.log("\n✅ Deploy successful!");
    console.log("Visit: http://43.138.213.164:8080");
  } else {
    console.log("\n❌ Health check failed. Checking logs...");
    const logs = await exec(ssh, "docker logs --tail 30 zhiyu-app 2>&1");
    console.log(logs.stdout.slice(-2000));
  }

  ssh.end();
}

run().catch((e) => console.error("ERROR:", e.message));
