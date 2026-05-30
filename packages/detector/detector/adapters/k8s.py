import asyncio


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
