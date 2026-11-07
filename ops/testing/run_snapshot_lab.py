"""Run native snapshot proofs against new synthetic Compose resources, then remove them."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from uuid import uuid4


def docker(*args, env=None):
    return subprocess.check_output(["docker", *args], text=True, env=env, timeout=30).strip()


def resources(project):
    selector = f"label=com.docker.compose.project={project}"
    return {
        "containers": docker("ps", "-aq", "--filter", selector).split(),
        "volumes": docker("volume", "ls", "-q", "--filter", selector).split(),
        "networks": docker("network", "ls", "-q", "--filter", selector).split(),
    }


def verify_results(results):
    suite = ET.parse(results / "snapshot-proofs.xml").getroot().find("testsuite")
    if suite is None or any(int(suite.get(key, "-1")) != expected for key, expected in
                            (("tests", 19), ("errors", 0), ("failures", 0), ("skipped", 0))):
        raise ValueError("Require all 19 snapshot tests with zero failures, errors and skips")
    for closed in (False, True):
        proof = json.loads((results / f"capture-closed-{str(closed).lower()}.json").read_text())
        assert all(proof[key] is True for key in
                   ("source_unchanged", "database_rows_equal", "lifecycle_consistency_verified"))
        manifest, quarantine = proof["manifest"], proof["quarantine"]
        assert manifest["backup_format_version"] == 3 and manifest["migration"] == "0008"
        assert manifest["capture_complete"] is True and len(manifest["lifecycle_store_sha256"]) == 5
        assert quarantine["status"] == "quarantined"
        assert quarantine["quota"] == {"issued_count": 4, "closed": closed}
        assert quarantine["documents_verified"] == 1 and quarantine["lifecycle_stores_restored"] == 5
        assert all(quarantine[key] is False for key in
                   ("api_attached", "opening_authorized", "s2_recovery_authorized",
                    "critical_mutations_allowed"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-image", required=True)
    parser.add_argument("--database-image", required=True)
    parser.add_argument("--results", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    assert all(path.name.endswith(".example") or path.name == ".env.example"
               for path in root.glob(".env*")), "Do not mount non-example environment files"
    assert docker("info", "--format", "{{.OSType}}") == "linux"
    images = {}
    for name, image in (("api", args.runner_image), ("db", args.database_image)):
        images[name] = json.loads(docker("image", "inspect", image))[0]["Id"]
    project = "documind-snapshot-" + uuid4().hex[:12]
    assert not any(resources(project).values()), "Project must not exist"
    args.results.mkdir(parents=True, exist_ok=False)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("COMPOSE_")}
    env.update(SNAPSHOT_LAB_PROJECT=project, SNAPSHOT_LAB_API_IMAGE=images["api"],
               SNAPSHOT_LAB_DB_IMAGE=images["db"])
    evidence = {"project": project, "images": images, "before": resources(project)}
    with tempfile.TemporaryDirectory(prefix="documind-snapshot-control-") as temporary:
        empty_env = Path(temporary) / "empty.env"
        empty_env.write_text("", encoding="utf-8")
        compose = ["compose", "-p", project, "--env-file", str(empty_env),
                   "-f", str(root / "ops" / "testing" / "compose.snapshot-lab.yaml")]
        config = json.loads(docker(*compose, "config", "--format", "json", env=env))
        assert set(config["services"]) == {"db", "api", "web"}
        assert set(config["volumes"]) == {"source_pg", "documents", "lifecycle"}
        assert config["name"] == project
        assert all(network["internal"] for network in config["networks"].values())
        for volume in config["volumes"].values():
            assert not volume.get("external")
            assert volume["name"].startswith(project + "_")
            assert volume["labels"]["documind.snapshot-lab"] == project
            assert volume["driver"] == "local"
        assert config["volumes"]["source_pg"]["driver_opts"]["type"] == "tmpfs"
        assert not any(config["volumes"][name].get("driver_opts")
                       for name in ("documents", "lifecycle"))
        for service in config["services"].values():
            assert not service.get("ports") and not service.get("env_file")
            assert not service.get("privileged") and service["read_only"]
            assert all(mount["type"] == "volume" for mount in service.get("volumes", []))
        assert not ({volume["name"] for volume in config["volumes"].values()}
                    & set(docker("volume", "ls", "-q").split()))
        assert not ({network["name"] for network in config["networks"].values()}
                    & set(docker("network", "ls", "--format", "{{.Name}}").split()))
        assert not docker("ps", "-aq", "--filter", "name=^/" + project + "-proofs$")
        evidence["config"] = config
        code = 1
        try:
            subprocess.run(["docker", *compose, "up", "-d", "--wait", "db"],
                           env=env, check=True, timeout=120)
            identifiers = docker(*compose, "ps", "-q", "db", env=env).split()
            assert len(identifiers) == 1
            db = json.loads(docker("inspect", identifiers[0]))[0]
            assert db["Config"]["Labels"]["documind.snapshot-lab"] == project
            assert not db["HostConfig"]["PortBindings"]
            command = [
                "docker", "run", "--rm", "--name", project + "-proofs",
                "--label", "documind.snapshot-lab=" + project,
                "--user", "0:0", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--memory", "1536m",
                "--pids-limit", "256", "--network", "container:" + identifiers[0],
                "--tmpfs", "/tmp:rw,size=512m,mode=1777",
                "--mount", f"type=bind,source={root},target=/workspace,readonly",
                "--mount", f"type=bind,source={args.results.resolve()},target=/results",
                "--mount", "type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock",
                "--env", "DOCKER_HOST=unix:///var/run/docker.sock",
                "--env", "DOCUMIND_SNAPSHOT_LAB=isolated",
                "--env", "SNAPSHOT_LAB_PROJECT=" + project,
                "--env", "SNAPSHOT_LAB_API_IMAGE=" + images["api"],
                "--env", "SNAPSHOT_LAB_DB_IMAGE=" + images["db"],
                "--env", "AI_ENABLED=false", "--env", "OPENAI_API_KEY=",
                "--env", "REGISTRATION_MODE=disabled", "--entrypoint", "python",
                images["api"], "-m", "pytest", "-q", "-rs", "-p", "no:cacheprovider",
                "--require-no-skips", "--basetemp=/tmp/snapshot-proofs",
                "--junitxml=/results/snapshot-proofs.xml",
                "tests/test_public_beta_snapshot.py",
            ]
            code = subprocess.run(command, check=False, timeout=600).returncode
            evidence["pytest_exit"] = code
            if code == 0:
                verify_results(args.results)
        except Exception as exc:
            evidence["qualification_error"] = str(exc)
            raise
        finally:
            try:
                proofs = docker("ps", "-aq", "--filter", "name=^/" + project + "-proofs$")
                if proofs:
                    owned = json.loads(docker("inspect", proofs))[0]
                    assert owned["Config"]["Labels"]["documind.snapshot-lab"] == project
                    subprocess.run(["docker", "rm", "--force", proofs], check=True, timeout=30)
                subprocess.run(["docker", *compose, "down", "--volumes", "--remove-orphans"],
                               env=env, check=True, timeout=120)
                evidence["after"] = resources(project)
                assert not any(evidence["after"].values()), "Lab resources were not removed"
                assert not docker("ps", "-aq", "--filter", "name=^/" + project + "-proofs$")
            except Exception as exc:
                evidence["cleanup_error"] = str(exc)
                raise
            finally:
                (args.results / "lab-resources.json").write_text(
                    json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        raise SystemExit(code)


if __name__ == "__main__":
    main()
