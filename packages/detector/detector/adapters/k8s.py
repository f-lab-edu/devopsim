import asyncio

_DRY_RUN_FLAG = "--dry-run=server"


class K8sAdapter:
    async def _run(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "kubectl",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return f"kubectl exit {proc.returncode}\n{stderr.decode().strip()}"
        return stdout.decode()

    async def _run_write(self, args: list[str], *, dry_run: bool) -> str:
        if dry_run:
            args.append(_DRY_RUN_FLAG)
        return await self._run(*args)

    async def get(self, kind: str, namespace: str, name: str | None) -> str:
        args = ["get", kind]
        if name:
            args.append(name)
        args += ["-n", namespace, "-o", "yaml"]
        return await self._run(*args)

    async def describe(self, kind: str, namespace: str, name: str) -> str:
        return await self._run("describe", kind, name, "-n", namespace)

    async def logs(
        self,
        namespace: str,
        pod: str,
        container: str | None,
        tail_lines: int,
        previous: bool,
    ) -> str:
        args = ["logs", pod, "-n", namespace, f"--tail={tail_lines}"]
        if container:
            args += ["-c", container]
        if previous:
            args.append("--previous")
        return await self._run(*args)

    async def list_events(self, namespace: str, field_selector: str | None) -> str:
        args = ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"]
        if field_selector:
            args += ["--field-selector", field_selector]
        return await self._run(*args)

    async def rollout_history(self, kind: str, namespace: str, name: str, revision: int | None) -> str:
        args = ["rollout", "history", f"{kind}/{name}", "-n", namespace]
        if revision is not None:
            args.append(f"--revision={revision}")
        return await self._run(*args)

    async def restart_deployment(self, namespace: str, name: str, *, dry_run: bool) -> str:
        args = ["rollout", "restart", "deployment", name, "-n", namespace]
        return await self._run_write(args, dry_run=dry_run)

    async def scale_deployment(self, namespace: str, name: str, replicas: int, *, dry_run: bool) -> str:
        args = ["scale", "deployment", name, f"--replicas={replicas}", "-n", namespace]
        return await self._run_write(args, dry_run=dry_run)

    async def delete_pod(self, namespace: str, name: str, *, dry_run: bool) -> str:
        args = ["delete", "pod", name, "-n", namespace]
        return await self._run_write(args, dry_run=dry_run)
