from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    profile: str = Field(description="Profile whose browser runs the workflow; launched if stopped")
    variables: dict[str, str] = Field(
        default_factory=dict, description="Starting values for this run, over the workflow's own"
    )


class ChainRunRequest(BaseModel):
    profile: str = Field(
        description="Profile whose browser runs the workflows; launched if stopped"
    )
    workflows: list[str] = Field(
        min_length=1,
        max_length=20,
        description="Workflows to run one after the other in the same browser",
    )
    variables: dict[str, str] = Field(
        default_factory=dict,
        description="Starting values for this run, for each workflow that has the variable",
    )


class AISettingsUpdate(BaseModel):
    api_key: str | None = Field(
        None, max_length=500, description='Omit to keep the saved key; "" removes it'
    )
    base_url: str | None = Field(None, max_length=500)
    model: str | None = Field(None, max_length=200)
    system_prompt: str | None = Field(None, max_length=10_000)
    temperature: float | None = Field(None, ge=0, le=2)
    clear_temperature: bool = Field(False, description="Let the model use its default")


class AITestRequest(BaseModel):
    prompt: str = Field("Say hello in five words.", max_length=10_000)


class RecordStopRequest(BaseModel):
    save_as: str | None = Field(
        None,
        description="Save the recorded steps as this workflow. Without it the recording "
        "stops and stays as an unsaved draft.",
    )
    description: str = Field("", max_length=2_000)
    overwrite: bool = Field(False, description="Replace an existing workflow of that name")
    discard: bool = Field(False, description="Throw the recording away")
